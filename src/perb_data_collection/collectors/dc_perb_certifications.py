"""District of Columbia PERB certification index.

WHAT THIS FILE IS FOR
---------------------
Scrape the embedded DataTables certification listing at
casesearch.perb.dc.gov/?docType=Certifications (one HTML page, no pagination),
map PERB case-type codes into the shared canonical enum, then read each
certification document for the parties' roles, the certified representative
and the order date, and write a wide CSV.

The listing's Complainant / Respondent columns are procedural positions, not
roles. On a unit-modification petition the agency is the complainant; on
12-RC-02 the respondent cell is "Office of Unified Communications and National
Association of Government Employees, Local R3-07", the agency and the
intervening union in one string. And the petitioner is not the winner:
12-RC-02 was petitioned by the International Union of Public Employees and
certified NAGE Local R3-07. So:

* ``petitioner`` / ``respondent`` / ``agency`` / ``intervenor`` come from the
  document's own caption labels, each kept in its own column;
* ``certified_representative`` comes only from the operative "IT IS HEREBY
  CERTIFIED THAT" section, and is the union this row is evidence for;
* ``employer_name`` / ``union_name`` are decided by content
  (:mod:`perb_data_collection.party_roles`) when the document cannot be read,
  and ``union_name_source`` says which rule produced the union.

Scanned certifications have no text layer; they are OCR'd, and
``document_text_method`` records how the text was obtained.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.captions import joined, parse_labelled_caption
from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.dates import date_after, parse_month_abbr_stamp
from perb_data_collection.http import fetch_document_bytes, fetch_url, strip_html_text
from perb_data_collection.party_roles import (
    assign_roles,
    clean_party_text,
    is_union,
    split_side,
)
from perb_data_collection.pdf_probe import TEXT_METHOD_TEXT_LAYER, document_text

logger = logging.getLogger(__name__)

FLOW_NAME = "DC PERB Certifications Flow"
REPORT_PREFIX = "dc_perb_certifications"
AGENCY_CODE = "DC_PERB"
BASE_URL = "https://casesearch.perb.dc.gov"
LISTING_URL = f"{BASE_URL}/?docType=Certifications"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "certification_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "union_name_source",
    "listing_complainant",
    "listing_respondent",
    "petitioner",
    "respondent",
    "agency",
    "intervenor",
    "certified_representative",
    "certification_result",
    "document_text_method",
    "date_opened",
    "order_date",
    "order_date_raw",
    "order_date_source",
    "order_date_precision",
    "dc_register_cite",
    "document_name",
    "document_url",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_CASE_TYPE_MAP = {
    "RC": "RECOGNITION",
    "AC": "AMENDMENT_OF_CERTIFICATION",
    "RD": "DECERTIFICATION",
    "UC": "UNIT_CLARIFICATION",
    "UM": "UNIT_MODIFICATION",
    "UCN": "UNIT_MODIFICATION",
    "CU": "UNIT_MODIFICATION",
    "U": "ULP",
}

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
# The order body, near the signature block, prints its date fully spelled
# out on its own line, e.g. "July 17, 2025". This is the date the Board
# actually signed/issued the order.
_BODY_DATE_RE = re.compile(
    rf"\b(?:{_MONTH_NAMES})\s+\d{{1,2}},\s+\d{{4}}\b"
)
# The e-filing/received stamp at the top of the PDF uses an abbreviated
# month with no comma and a timestamp, e.g. "Jul 25 2025 07:46PM EDT". This
# is when the document was filed/received, not the date the order was
# issued -- in the sample read, it postdates the body date by over a week.
_STAMP_DATE_RE = re.compile(
    r"\b([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})\s+\d{1,2}:\d{2}[AP]M\s+\w+"
)
# The certification's own closing block: "BY ORDER OF THE PUBLIC EMPLOYEE
# RELATIONS BOARD / Washington, D.C. / December 5, 2018". A cover letter or a
# recital can carry other dates, so this block is read first.
_ORDER_BLOCK_ANCHORS: tuple[str, ...] = (
    r"BY\s+ORDER\s+OF\s+THE\s+PUBLIC\s+EMPLOYEE\s+RELATIONS\s+BOARD",
)


def _parse_order_date(text: str) -> tuple[str, str, str]:
    """Return (order_date ISO, order_date_raw, order_date_source).

    Prefers the certification's "BY ORDER OF THE BOARD" block, then the last
    date spelled out in the body, then the e-filing/received stamp. Returns
    empty strings when none is present or parseable.
    """
    block = date_after(text, _ORDER_BLOCK_ANCHORS, window=250)
    if block:
        return block.iso, block.raw, "order_block"

    body_matches = _BODY_DATE_RE.findall(text)
    if body_matches:
        raw = body_matches[-1]
        try:
            parsed = datetime.strptime(raw, "%B %d, %Y")
        except ValueError:
            pass
        else:
            return parsed.date().isoformat(), raw[:80], "body"

    stamp_match = _STAMP_DATE_RE.search(text)
    if stamp_match:
        month_abbr, day, year = stamp_match.groups()
        parsed_stamp = parse_month_abbr_stamp(month_abbr, day, year)
        if parsed_stamp:
            return parsed_stamp.isoformat(), stamp_match.group(0)[:80], "stamp"

    return "", "", ""


# --- the certification document: caption roles and the operative section ----

# OCR reads the capital I of an old typescript as T ("Tn the Matter of").
_CAPTION_START_RE = re.compile(r"\b[IT]n\s+the\s+matter\s+of\s*:?\)?", flags=re.I)
_CAPTION_END_RE = re.compile(
    r"^\s*(?:corrected\s+)?certificat(?:e|ion)\s+of\s+representati"
    r"|^\s*decision\s+and\s+order\b"
    r"|^\s*a\s+representation\s+proceeding\b"
    r"|^\s*it\s+is\s+hereby\s+certified\b",
    flags=re.I,
)
_CAPTION_NOISE_RES: tuple[re.Pattern[str], ...] = (
    # OCR misreads: "7ERB Case No.", "Certification Ne. 10".
    re.compile(r"[P7]ERB\s+Case\s+No[.:]?\s*[\w-]*", flags=re.I),
    re.compile(r"Certification\s+N[oe][.:]?\s*\d*", flags=re.I),
    re.compile(r"CORRECTED\s+COPY", flags=re.I),
)


def parse_caption_roles(text: str) -> dict[str, str]:
    """Read the caption's labelled parties into petitioner/respondent/agency/intervenor.

    Returns empty strings for roles the caption does not label. Nothing is
    assigned by position: a name only lands in a column when the caption's own
    label follows it.
    """
    found = parse_labelled_caption(
        text, start_re=_CAPTION_START_RE, end_re=_CAPTION_END_RE, noise=_CAPTION_NOISE_RES
    )
    return {role: joined(found[role]) for role in ("petitioner", "respondent", "agency", "intervenor")}


_CERT_SECTION_RE = re.compile(
    r"IT\s+IS\s+HEREBY\s+CERTIFIED\s*(?:THAT)?\s*:?\s*(?P<body>.{0,700})",
    flags=re.I | re.S,
)
# Tolerates a text layer that lost its word spaces ("hasbeendesignated").
_DESIGNATED_RE = re.compile(
    r"^(?P<name>.+?)\s*,?\s*(?:has|have)\s*been\s*(?:duly\s*)?(?:designated|selected|chosen)",
    flags=re.I | re.S,
)
# Older certifications: "IT IS HEREBY CERTIFIED that a majority of the valid
# ballots have been cast for the Fraternal Order of Police ... and that".
_BALLOTS_CAST_FOR_RE = re.compile(
    r"majority\s+of\s+the\s+valid\s+ballots\s+(?:has|have)\s+been\s+cast\s+for\s+"
    r"(?P<name>.+?)(?:\s*,?\s+and\s+that\b|\s*,?\s+(?:and\s+)?(?:said|which)\s+labor\b|\.\s)",
    flags=re.I | re.S,
)
_NO_REPRESENTATIVE_RE = re.compile(
    r"\b(?:no\s+(?:labor\s+organization|exclusive\s+representative|representative)"
    r"|(?:has|have)\s+not\s+been\s+cast\s+for\s+any"
    r"|not\s+(?:selected|designated)\s+(?:any|a)\s+(?:labor\s+organization|representative))",
    flags=re.I,
)
# Running page headers a multi-page certification repeats mid-sentence.
_PAGE_HEADER_RE = re.compile(
    r"^\s*(?:certificat(?:e|ion)\s+of\s+representati\w*|PERB\s+Case\s+No\.?.*|"
    r"page\s+\d+(?:\s+of\s+\d+)?|certification\s+no\.?.*)\s*$",
    flags=re.I | re.M,
)

CERTIFIED = "representative_certified"
NO_REPRESENTATIVE = "no_representative"
SECTION_NOT_FOUND = "section_not_found"
DOCUMENT_UNREADABLE = "document_unreadable"


def parse_certified_representative(text: str) -> tuple[str, str]:
    """Return ``(certified_representative, certification_result)``.

    Only the operative section counts. The caption and the recitals name the
    petitioner and the intervenor too, and on a contested election the
    petitioner is not the winner.
    """
    if not text or not text.strip():
        return "", DOCUMENT_UNREADABLE
    flat = _PAGE_HEADER_RE.sub(" ", text)
    match = _CERT_SECTION_RE.search(flat)
    if not match:
        return "", SECTION_NOT_FOUND
    body = re.sub(r"\s+", " ", match.group("body")).strip()
    designated = _DESIGNATED_RE.match(body)
    if designated and not _NO_REPRESENTATIVE_RE.search(designated.group("name")):
        name = clean_party_text(designated.group("name"))
        if name and not re.match(r"(?i)a\s+majority\b", name):
            return name[:240], CERTIFIED
    cast_for = _BALLOTS_CAST_FOR_RE.search(body)
    if cast_for:
        name = clean_party_text(cast_for.group("name"))
        if name:
            return name[:240], CERTIFIED
    if _NO_REPRESENTATIVE_RE.search(body[:400]):
        return "", NO_REPRESENTATIVE
    return "", SECTION_NOT_FOUND


def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _native_code(case_type: str) -> str:
    match = re.match(r"^([A-Z]+)\b", case_type.strip(), flags=re.I)
    return match.group(1).upper() if match else case_type.strip().upper()

def _canonical(case_type: str) -> str:
    code = _native_code(case_type)
    return _CASE_TYPE_MAP.get(code, "CERTIFICATION")

def _listing_roles(complainant: str, respondent: str) -> tuple[str, str]:
    """Employer and union from the listing, decided by content.

    The employer is every public body named on either side. The union is set
    only when the listing names exactly one labour organisation; when it names
    two (a petitioner and an incumbent) which one represents the unit is the
    certification's outcome, and only the document says it.
    """
    employer, union = assign_roles(complainant, respondent)
    if not employer:
        publics = split_side(complainant)[0] + split_side(respondent)[0]
        employer = "; ".join(publics)
    return employer[:240], union[:240]


def apply_document(row: dict[str, str], text: str, method: str) -> dict[str, str]:
    """Fold one certification document's roles, outcome and date into ``row``."""
    out = dict(row)
    out["document_text_method"] = method
    roles = parse_caption_roles(text)
    out.update(roles)
    representative, result = parse_certified_representative(text)
    out["certified_representative"] = representative
    out["certification_result"] = result
    if representative:
        out["union_name"] = representative
        out["union_name_source"] = "certification"
    elif result == NO_REPRESENTATIVE:
        # The Board certified that no representative was chosen. Naming the
        # petitioner as the union would file a loss as a win.
        out["union_name"] = ""
        out["union_name_source"] = "no_representative"
    else:
        # The operative section could not be read. When the caption names two
        # labour organisations (a petitioner and an incumbent or intervenor),
        # which one won is exactly what is unknown, and the listing's guess
        # picked the loser on 81-RC-05. Leave the union empty.
        caption_unions = [
            name
            for key in ("petitioner", "respondent", "intervenor")
            for name in roles[key].split("; ")
            if name and is_union(name)
        ]
        if len(caption_unions) >= 2:
            out["union_name"] = ""
            out["union_name_source"] = "contested_unresolved"
    agency = roles["agency"] or (
        roles["respondent"] if split_side(roles["respondent"])[0] and not split_side(roles["respondent"])[1] else ""
    )
    if agency:
        out["employer_name"] = agency[:240]
    order_date, order_date_raw, order_date_source = _parse_order_date(text)
    out["order_date"] = order_date
    out["order_date_raw"] = order_date_raw
    out["order_date_source"] = order_date_source
    out["order_date_precision"] = "day" if order_date else ""
    return out


def parse_certification_table(html: str, *, scraped_at: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 7:
            continue
        case_number = strip_html_text(cells[0])
        if not case_number or case_number.lower() == "perb case #":
            continue
        date_opened = strip_html_text(cells[1])
        certification_number = strip_html_text(cells[2])
        native_case_type = strip_html_text(cells[3])
        # The index carries stray list punctuation: a terminal comma on a
        # handful of agency names and a trailing ", vs." on complainants.
        complainant = clean_party_text(strip_html_text(cells[4]).rstrip(","))
        respondent = clean_party_text(strip_html_text(cells[5]).rstrip(","))
        employer, union = _listing_roles(complainant, respondent)
        cite = strip_html_text(cells[6]) if len(cells) > 6 else ""
        document_name = strip_html_text(cells[7]) if len(cells) > 7 else ""
        href_match = re.search(r'href="([^"]+)"', row_html, flags=re.I)
        document_url = _absolute_url(href_match.group(1)) if href_match else ""
        file_id_match = re.search(
            r"fileid=\{?([0-9A-Fa-f-]{36})\}?", document_url, flags=re.I
        )
        file_id = file_id_match.group(1).upper() if file_id_match else ""

        # One case can have multiple certification PDFs / fileids.
        cert_part = certification_number or "NOCERT"
        doc_part = file_id or document_name or "NODOC"
        row_key = f"{AGENCY_CODE}:{case_number}:{cert_part}:{doc_part}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "certification_number": certification_number,
                "canonical_case_type": _canonical(native_case_type),
                "native_case_type": native_case_type or _native_code(native_case_type),
                "employer_name": employer,
                "union_name": union,
                "union_name_source": "listing_roles" if union else "",
                "listing_complainant": complainant,
                "listing_respondent": respondent,
                "petitioner": "",
                "respondent": "",
                "agency": "",
                "intervenor": "",
                "certified_representative": "",
                "certification_result": "",
                "document_text_method": "",
                "date_opened": date_opened,
                "order_date": "",
                "order_date_raw": "",
                "order_date_source": "",
                "order_date_precision": "",
                "dc_register_cite": cite,
                "document_name": document_name,
                "document_url": document_url,
                # This board's jurisdiction is the District, not a city parsed
                # from the agency name. The former parser turned values such as
                # "District of Columbia Department of Aging..." into the bogus
                # city "Department of Aging...", preventing geographic matches.
                "jurisdiction_city": "Washington",
                "jurisdiction_state": "DC",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": LISTING_URL,
                "source_url": document_url or LISTING_URL,
                "scraped_at": scraped_at,
            }
        )
    return rows

def _read_document(
    document_url: str,
    *,
    delay_seconds: float,
    fetch_pdf: Any,
    pdf_to_text: Any,
) -> tuple[str, str]:
    """Fetch one certification document; return ``(text, method)``.

    Retries the fetch once. After a second failure the method is
    ``fetch_failed`` and the row keeps its listing values: a failed read is not
    a document that says nothing.
    """
    data: bytes | None = None
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            data = fetch_pdf(document_url, delay_seconds=delay_seconds)
            break
        except Exception as exc:  # noqa: BLE001 - deliberately broad, logged below
            last_exc = exc
    if data is None:
        logger.warning(
            "Could not fetch certification document after retry: %s (%s)",
            document_url,
            last_exc,
        )
        return "", "fetch_failed"
    if pdf_to_text is not None:
        return pdf_to_text(data) or "", TEXT_METHOD_TEXT_LAYER
    return document_text(data)


def scrape_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    read_documents: bool = True,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(LISTING_URL, delay_seconds=delay_seconds)
    rows = parse_certification_table(html, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"DC PERB certifications page parsed 0 rows: {LISTING_URL}")

    if read_documents:
        pdf_fetcher = fetch_pdf or fetch_document_bytes
        counts: dict[str, int] = {}
        for index, row in enumerate(rows):
            document_url = row.get("document_url", "")
            if not document_url:
                counts["no_document"] = counts.get("no_document", 0) + 1
                continue
            text, method = _read_document(
                document_url,
                delay_seconds=delay_seconds,
                fetch_pdf=pdf_fetcher,
                pdf_to_text=pdf_to_text,
            )
            if method == "fetch_failed":
                rows[index] = {**row, "document_text_method": method}
            else:
                rows[index] = apply_document(row, text, method)
            result = rows[index].get("certification_result") or method
            counts[result] = counts.get(result, 0) + 1
        logger.warning("DC PERB certifications: document outcomes %s", counts)

    rows.sort(key=lambda row: row["case_number"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)
