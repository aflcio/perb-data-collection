"""District of Columbia PERB certification index.

WHAT THIS FILE IS FOR
---------------------
Scrape the embedded DataTables certification listing at
casesearch.perb.dc.gov/?docType=Certifications (one HTML page, no pagination),
map PERB case-type codes into the shared canonical enum, then write a wide CSV.

Employer is the Respondent (agency); Complainant is typically the union.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

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

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _native_code(case_type: str) -> str:
    match = re.match(r"^([A-Z]+)\b", case_type.strip(), flags=re.I)
    return match.group(1).upper() if match else case_type.strip().upper()

def _canonical(case_type: str) -> str:
    code = _native_code(case_type)
    return _CASE_TYPE_MAP.get(code, "CERTIFICATION")

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(r"^District of Columbia\s+", "", name, flags=re.I)
    name = re.sub(r"^D\.?C\.?\s+", "", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

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
                "dc_register_cite": cite,
                "document_name": document_name,
                "document_url": document_url,
                "jurisdiction_city": _jurisdiction_city(respondent),
                "jurisdiction_state": "DC",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": LISTING_URL,
                "source_url": document_url or LISTING_URL,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(LISTING_URL, delay_seconds=delay_seconds)
    rows = parse_certification_table(html, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"DC PERB certifications page parsed 0 rows: {LISTING_URL}")
    rows.sort(key=lambda row: row["case_number"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)
