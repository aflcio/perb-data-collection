"""District of Columbia PERB certification index.

WHAT THIS FILE IS FOR
---------------------
Scrape the embedded DataTables certification listing at
casesearch.perb.dc.gov/?docType=Certifications (one HTML page, no pagination),
map PERB case-type codes into the shared canonical enum, then write a wide CSV.

Employer is the Respondent (agency); Complainant is typically the union.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, fetch_bytes, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

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
    "date_opened",
    "order_date",
    "order_date_raw",
    "order_date_source",
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
_MONTH_ABBR_TO_NUM = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_order_date(text: str) -> tuple[str, str, str]:
    """Return (order_date ISO, order_date_raw, order_date_source).

    Prefers the date spelled out in the order body over the e-filing/
    received stamp; falls back to the stamp only when no body date is
    found. Returns empty strings when neither is present or unparseable.
    """
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
        month = _MONTH_ABBR_TO_NUM.get(month_abbr[:3].title())
        if month:
            try:
                parsed = datetime(int(year), month, int(day))
            except ValueError:
                pass
            else:
                raw = stamp_match.group(0)[:80]
                return parsed.date().isoformat(), raw, "stamp"

    return "", "", ""


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Run pdftotext -l 2 -layout over PDF bytes; "" if no readable text."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(pdf_bytes)
        handle.flush()
        try:
            completed = subprocess.run(
                ["pdftotext", "-l", "2", "-layout", handle.name, "-"],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pdftotext is required to parse DC PERB certification PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "pdftotext could not read document (no text layer or not a "
                "PDF): %s",
                exc.stderr or exc.stdout or exc,
            )
            return ""
        return completed.stdout


def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _native_code(case_type: str) -> str:
    match = re.match(r"^([A-Z]+)\b", case_type.strip(), flags=re.I)
    return match.group(1).upper() if match else case_type.strip().upper()

def _canonical(case_type: str) -> str:
    code = _native_code(case_type)
    return _CASE_TYPE_MAP.get(code, "CERTIFICATION")

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
        complainant = strip_html_text(cells[4]).rstrip(",")
        # The index carries a stray terminal comma on a handful of agency
        # names. It is list punctuation, not part of the employer name (the
        # complainant column has the same artifact).
        respondent = strip_html_text(cells[5]).rstrip(",")
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
                "employer_name": respondent,
                "union_name": complainant,
                "date_opened": date_opened,
                "order_date": "",
                "order_date_raw": "",
                "order_date_source": "",
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

def _read_order_date(
    document_url: str,
    *,
    delay_seconds: float,
    fetch_pdf: Any,
    pdf_to_text: Any,
) -> tuple[str, str, str]:
    """Fetch one certification PDF and parse its order date.

    Retries the fetch once on failure; on repeated failure returns empty
    values so the caller leaves the row's date columns blank and moves on.
    """
    pdf_bytes: bytes | None = None
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            pdf_bytes = fetch_pdf(document_url, delay_seconds=delay_seconds)
            break
        except Exception as exc:  # noqa: BLE001 - deliberately broad, logged below
            last_exc = exc
            if attempt == 0:
                continue
    if pdf_bytes is None:
        logger.warning(
            "Could not fetch certification document after retry, leaving "
            "order_date blank: %s (%s)",
            document_url,
            last_exc,
        )
        return "", "", ""

    text = pdf_to_text(pdf_bytes)
    if not text:
        return "", "", ""
    return _parse_order_date(text)


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
        pdf_fetcher = fetch_pdf or fetch_bytes
        text_extractor = pdf_to_text or _pdf_to_text
        found = 0
        missing = 0
        for row in rows:
            document_url = row.get("document_url", "")
            if not document_url:
                missing += 1
                continue
            order_date, order_date_raw, order_date_source = _read_order_date(
                document_url,
                delay_seconds=delay_seconds,
                fetch_pdf=pdf_fetcher,
                pdf_to_text=text_extractor,
            )
            row["order_date"] = order_date
            row["order_date_raw"] = order_date_raw
            row["order_date_source"] = order_date_source
            if order_date:
                found += 1
            else:
                missing += 1
        logger.warning(
            "DC PERB certifications: order_date read for %d/%d rows (%d without a "
            "usable document date)",
            found,
            len(rows),
            missing,
        )

    rows.sort(key=lambda row: row["case_number"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)
