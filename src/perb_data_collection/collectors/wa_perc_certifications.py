"""Washington PERC pending representation cases.

WHAT THIS FILE IS FOR
---------------------
Scrape PERC's pending representation case table (employer, case number, status,
filed date), then run shared state-PERB ACE (GeoCensus) into Redshift.

Decisia "Certification" advanced search (typ=103) is currently CAPTCHA/WAF
gated from this host; pending cases on perc.wa.gov remain the shippable feed.

Source: https://perc.wa.gov/pending-representation-cases/
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "WA PERC Pending Representation Flow"
REPORT_PREFIX = "wa_perc_certifications"
AGENCY_CODE = "WA_PERC"
BASE_URL = "https://perc.wa.gov"
LISTING_URL = f"{BASE_URL}/pending-representation-cases/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "case_status",
    "date_filed",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "document_title",
    "pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

def _parse_listing_table(html: str, *, scraped_at: str) -> list[dict[str, str]]:
    table_match = re.search(r"<table[^>]*>(.*?)</table>", html, flags=re.I | re.S)
    if not table_match:
        return []

    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        date_filed = strip_html_text(cells[0])
        employer_cell = cells[1]
        employer_name = strip_html_text(employer_cell)
        case_number = strip_html_text(cells[2])
        case_status = strip_html_text(cells[3])
        if not case_number or case_number.lower() == "case number":
            continue
        if not employer_name:
            continue

        pdf_match = re.search(r'href="([^"]+\.pdf[^"]*)"', employer_cell, flags=re.I)
        pdf_url = urljoin(BASE_URL, pdf_match.group(1)) if pdf_match else ""
        row_key = f"{AGENCY_CODE}:{case_number}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "Pending Representation",
                "employer_name": employer_name,
                "union_name": "",
                "case_status": case_status,
                "date_filed": date_filed,
                "jurisdiction_city": "",
                "jurisdiction_state": "WA",
                "employer_street": "",
                "employer_zip": "",
                "document_title": f"{employer_name} ({case_number})",
                "pdf_url": pdf_url,
                "source_page_url": LISTING_URL,
                "source_url": pdf_url or LISTING_URL,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    """Scrape pending representation cases (Batch 2 shippable WA feed)."""
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(LISTING_URL, delay_seconds=delay_seconds)
    rows = _parse_listing_table(html, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"WA PERC pending-representation page parsed 0 rows: {LISTING_URL}")
    rows.sort(key=lambda row: (row["date_filed"], row["case_number"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

