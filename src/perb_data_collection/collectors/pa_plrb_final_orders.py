"""Pennsylvania PLRB Final Orders.

WHAT THIS FILE IS FOR
---------------------
PA.gov publishes PLRB Final Orders as year-indexed HTML lists with PDF links
(Union v. Employer titles). Walk the index → each year page, recover case
numbers from PERA/PF/PLRA-style filename tokens, then run shared state-PERB
ACE (GeoCensus) on employer jurisdiction hints.

The listing prints each order's docket number on the line under its link
("PF-R-25-56-W"). That is the case number; the filename token is only a
fallback, and ``row_key`` keeps the filename-derived token so an existing key
never moves. The docket's second segment is the case type (R representation,
C charge, U unit clarification, D decertification, A arbitration).

Each order PDF is then read for the date the Board sealed it ("SEALED, DATED
and MAILED ... this seventeenth day of March, 2026"), the employer named in an
"In the Matter of the Employes of X" caption, the petitioning union on a
representation matter, and whether the Board dismissed it. When the PDF cannot
be read the row keeps ``decision_year`` and no date, never a January 1.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

import logging

from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.dates import date_after
from perb_data_collection.http import fetch_document_bytes, fetch_url, strip_html_text
from perb_data_collection.party_roles import assign_roles, clean_party_text, is_union
from perb_data_collection.pdf_probe import TEXT_METHOD_TEXT_LAYER, document_text

logger = logging.getLogger(__name__)

FLOW_NAME = "PA PLRB Final Orders Flow"
REPORT_PREFIX = "pa_plrb_final_orders"
AGENCY_CODE = "PA_PLRB"
BASE_URL = "https://www.pa.gov"
INDEX_URL = (
    f"{BASE_URL}/agencies/dli/programs-services/labor-management-relations/"
    "pennsylvania-labor-relations-board/plrb-final-orders"
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "decision_year",
    "docket_number",
    "employer_name",
    "union_name",
    "party_source",
    "petitioner",
    "order_disposition",
    "order_date",
    "order_date_raw",
    "order_date_source",
    "order_date_precision",
    "document_text_method",
    "document_title",
    "pdf_url",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_YEAR_HREF_RE = re.compile(
    r"""href=['"]([^'"]*plrb-final-orders/(?:20\d{2})[^'"]*)['"]""",
    flags=re.I,
)
_YEAR_FROM_PATH_RE = re.compile(r"/(20\d{2})(?:-plrb)?-final-orders", flags=re.I)
_PDF_ANCHOR_RE = re.compile(
    r"""<a[^>]+href=['"]([^'"]+\.pdf[^'"]*)['"][^>]*>(.*?)</a>""",
    flags=re.I | re.S,
)
_CASE_FROM_FILE_RE = re.compile(
    r"(?P<prefix>pera|pf|plra|plrb)-(?P<body>[a-z]?-?\d{2}-\d+[a-z]?-[a-z])",
    flags=re.I,
)
_V_SPLIT_RE = re.compile(r"\s+v\.?\s+", flags=re.I)
# "PF-R-25-56-W", "PERA-C-24-119-E", "PLRA-C-25-16-E": board prefix, case-type
# letter(s), year, sequence, region.
_DOCKET_RE = re.compile(r"\b(?:PERA|PF|PLRA|PLRB|PERB)-[A-Z]{1,2}-\d{2}-\d+-[A-Z]\b")
_DOCKET_TYPE: dict[str, str] = {
    "R": "CERTIFICATION",
    "C": "ULP",
    "U": "UNIT_CLARIFICATION",
    "D": "DECERTIFICATION",
    "A": "ARBITRATION",
}

def _absolute_url(href: str, base: str = BASE_URL) -> str:
    return urljoin(base.rstrip("/") + "/", href)

def list_year_pages(html: str) -> list[tuple[str, str]]:
    """Return unique (year, absolute_url) pairs, newest first."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in _YEAR_HREF_RE.findall(html):
        match = _YEAR_FROM_PATH_RE.search(href)
        if not match:
            continue
        year = match.group(1)
        # Skip the index itself (.../plrb-final-orders) — year must be in the leaf slug.
        leaf = href.rstrip("/").rsplit("/", 1)[-1]
        if not re.match(rf"{year}(?:-plrb)?-final-orders$", leaf, flags=re.I):
            continue
        if year in seen:
            continue
        seen.add(year)
        found.append((year, _absolute_url(href, BASE_URL)))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return found

def _canonical(title: str, case_number: str) -> str:
    docket = _DOCKET_RE.search(case_number.upper())
    if docket:
        kind = docket.group(0).split("-")[1]
        if kind in _DOCKET_TYPE:
            return _DOCKET_TYPE[kind]
    lowered = f"{title} {case_number}".lower()
    if "decertif" in lowered:
        return "DECERTIFICATION"
    if "unit clarification" in lowered or "clarif" in lowered:
        return "UNIT_CLARIFICATION"
    if re.search(r"\bpera-r\b|\brepresentation\b|\belection\b", lowered):
        return "CERTIFICATION"
    if re.search(r"\bpera-c\b|\bunfair\b|\bulp\b", lowered):
        return "ULP"
    if "fact finding" in lowered or "fact-finding" in lowered:
        return "FACT_FINDING"
    if "interest arbitration" in lowered or re.search(r"\bpera-a\b", lowered):
        return "ARBITRATION"
    return "ULP"

def _parties_from_title(title: str) -> tuple[str, str]:
    """Return (employer_name, union_name) decided by content, never by position.

    PLRB final orders are captioned complainant v. respondent, so the union is
    on the left only on union-filed charges.  Employer-filed charges put the
    township on the left, and duty-of-fair-representation charges put an
    individual there.  Anything the tokens do not prove stays empty.
    """
    parts = _V_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    employer, union = assign_roles(parts[0], parts[1])
    return employer[:160], union[:160]

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(r"^(City|Borough|Township|County)\s+of\s+", "", name, flags=re.I)
    name = re.sub(r"\s+County\b.*$", " County", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

def _case_from_filename(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    match = _CASE_FROM_FILE_RE.search(stem)
    if not match:
        # e.g. allegheny-co-pera-a-24-178-w
        loose = re.search(r"(pera|pf|plra)-[a-z]?-?\d{2}-\d+[a-z]?-[a-z]", stem, flags=re.I)
        if not loose:
            return stem[:60]
        token = loose.group(0)
    else:
        token = match.group(0)
    return token.upper().replace("--", "-")

def parse_year_page(
    html: str,
    *,
    decision_year: str,
    page_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in _PDF_ANCHOR_RE.finditer(html):
        href, raw_label = anchor.group(1), anchor.group(2)
        pdf_url = _absolute_url(href, page_url)
        # Keep final-order PDFs; skip forms/agendas in shared nav
        if "final-orders" not in pdf_url.lower() and "/documents/" not in pdf_url.lower():
            continue
        if "/form/" in pdf_url.lower() or "annual-report" in pdf_url.lower():
            continue
        key = pdf_url.lower()
        if key in seen:
            continue
        seen.add(key)
        title = strip_html_text(raw_label)
        if not title:
            continue
        filename = unquote(pdf_url.rsplit("/", 1)[-1])
        file_case = _case_from_filename(filename)
        # The docket line printed under the link, before the next link.
        after = html[anchor.end() : anchor.end() + 400]
        after = re.split(r"(?i)<a\s|</p>|</li>", after, maxsplit=1)[0]
        docket_match = _DOCKET_RE.search(strip_html_text(after).upper())
        docket = docket_match.group(0) if docket_match else ""
        case_number = docket or file_case
        employer, union = _parties_from_title(title)
        native = case_number.split("-")[0] if "-" in case_number else "ORDER"
        # Keyed on the filename token, as before, so a key never moves when the
        # listing's docket line is read.
        row_key = f"{AGENCY_CODE}:{decision_year}:{file_case}:{filename[:50]}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": _canonical(title, case_number),
                "native_case_type": native,
                "decision_year": decision_year,
                "docket_number": docket,
                "employer_name": employer,
                "union_name": union,
                "party_source": "title" if (employer or union) else "",
                "petitioner": "",
                "order_disposition": "",
                "order_date": "",
                "order_date_raw": "",
                "order_date_source": "",
                "order_date_precision": "",
                "document_text_method": "",
                "document_title": title,
                "pdf_url": pdf_url,
                "jurisdiction_city": _jurisdiction_city(employer) if employer else "",
                "jurisdiction_state": "PA",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": page_url,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

# --- the final order document ------------------------------------------------

_SEALED_ANCHORS: tuple[str, ...] = (r"SEALED,?\s+DATED\s+and\s+MAILED",)
_EMPLOYES_OF_RE = re.compile(
    r"IN\s+THE\s+MATTER\s+OF\s+THE\s+EMPLOY(?:E)?S\s+OF\s+(?P<employer>.+?)\s*(?:\n\s*\n|:|Case\s+No)",
    flags=re.I | re.S,
)
_DOC_DOCKET_RE = re.compile(r"Case\s+No\.?\s*(?P<docket>(?:PERA|PF|PLRA|PLRB|PERB)-[A-Z]{1,2}-\d{2}-\d+-[A-Z])", re.I)
# "... was filed with the Pennsylvania Labor Relations Board (Board) on
# October 29, 2025, by Teamsters Local No. 205, affiliated with ..."
_FILED_BY_RE = re.compile(
    r"filed\s+with\s+the\s+Pennsylvania\s+Labor\s+Relations\s+Board[^.]{0,120}?\bby\s+"
    r"(?:the\s+)?(?P<name>[A-Z][^,(;]{3,120}?)\s*(?:,|\()",
    flags=re.S,
)
_ORDER_SECTION_RE = re.compile(r"HEREBY\s+ORDERS\s+AND\s+DIRECTS(?P<body>.{0,900})", re.I | re.S)


def parse_order_document(text: str) -> dict[str, str]:
    """Docket, employer, petitioning union, disposition and the sealed date."""
    out = {
        "docket_number": "",
        "employer_name": "",
        "petitioner": "",
        "order_disposition": "",
        "order_date": "",
        "order_date_raw": "",
        "order_date_source": "",
        "order_date_precision": "",
    }
    flat = re.sub(r"[ \t]+", " ", text or "")
    docket = _DOC_DOCKET_RE.search(flat)
    if docket:
        out["docket_number"] = docket.group("docket").upper()
    employes = _EMPLOYES_OF_RE.search(flat)
    if employes:
        out["employer_name"] = clean_party_text(re.sub(r"\s+", " ", employes.group("employer"))).title()[:240]
    filed_by = _FILED_BY_RE.search(flat)
    if filed_by:
        name = clean_party_text(re.sub(r"\s+", " ", filed_by.group("name")))
        if is_union(name):
            out["petitioner"] = name[:240]
    order = _ORDER_SECTION_RE.search(flat)
    if order:
        body = order.group("body").lower()
        if "dismiss" in body:
            out["order_disposition"] = "dismissed"
        elif "certif" in body:
            out["order_disposition"] = "certified"
        elif "sustain" in body:
            out["order_disposition"] = "sustained"
    hit = date_after(flat, _SEALED_ANCHORS, window=500)
    if hit:
        out["order_date"] = hit.iso
        out["order_date_raw"] = hit.raw
        out["order_date_source"] = "sealed_dated_mailed"
        out["order_date_precision"] = hit.precision
    return out


def apply_document(row: dict[str, str], text: str, method: str) -> dict[str, str]:
    out = dict(row)
    out["document_text_method"] = method
    parsed = parse_order_document(text)
    for key in ("petitioner", "order_disposition", "order_date", "order_date_raw",
                "order_date_source", "order_date_precision"):
        out[key] = parsed[key]
    if parsed["docket_number"] and not out.get("docket_number"):
        out["docket_number"] = parsed["docket_number"]
        out["case_number"] = parsed["docket_number"]
        out["canonical_case_type"] = _canonical(out.get("document_title", ""), parsed["docket_number"])
    if parsed["employer_name"] and not out.get("employer_name"):
        out["employer_name"] = parsed["employer_name"]
        out["jurisdiction_city"] = _jurisdiction_city(parsed["employer_name"])
        out["party_source"] = "document"
    if parsed["petitioner"] and not out.get("union_name"):
        out["union_name"] = parsed["petitioner"]
        out["party_source"] = "document"
    return out


def read_order_documents(
    rows: list[dict[str, str]],
    *,
    delay_seconds: float,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
) -> dict[str, int]:
    fetcher = fetch_pdf or fetch_document_bytes
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        url = row.get("pdf_url") or ""
        try:
            data = fetcher(url, delay_seconds=delay_seconds)
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not end the run
            logger.warning("PA PLRB order fetch failed: %s (%s)", url, exc)
            rows[index] = {**row, "document_text_method": "fetch_failed"}
            counts["fetch_failed"] = counts.get("fetch_failed", 0) + 1
            continue
        if pdf_to_text is not None:
            text, method = pdf_to_text(data) or "", TEXT_METHOD_TEXT_LAYER
        else:
            text, method = document_text(data)
        rows[index] = apply_document(row, text, method)
        key = f"{method}:{'dated' if rows[index]['order_date'] else 'undated'}"
        counts[key] = counts.get(key, 0) + 1
    logger.warning("PA PLRB final orders: document outcomes %s", counts)
    return counts


def scrape_orders(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    read_documents: bool = True,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    index_html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    years = list_year_pages(index_html)
    if not years:
        raise RuntimeError(f"PA PLRB final orders index found 0 year pages: {INDEX_URL}")

    rows: list[dict[str, str]] = []
    for year, page_url in years:
        page_html = fetcher(page_url, delay_seconds=delay_seconds)
        rows.extend(
            parse_year_page(
                page_html,
                decision_year=year,
                page_url=page_url,
                scraped_at=scraped_at,
            )
        )

    if not rows:
        raise RuntimeError("PA PLRB year pages parsed 0 final-order PDFs")
    if read_documents:
        read_order_documents(
            rows, delay_seconds=delay_seconds, fetch_pdf=fetch_pdf, pdf_to_text=pdf_to_text
        )
    rows.sort(key=lambda row: (row["decision_year"], row["case_number"], row["pdf_url"]), reverse=True)
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_orders(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

