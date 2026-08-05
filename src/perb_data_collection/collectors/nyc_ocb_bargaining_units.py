"""NYC Office of Collective Bargaining bargaining-unit roster → Redshift (wide).

WHAT THIS FILE IS FOR
---------------------
Scrape the public BOC bargaining-units HTML table at ocb-nyc.org/bargaining/
(Certification #, colloquial name, union, DCAS CBU#, titles PDF). Land raw
registry rows in Redshift. ACE is deferred until real agency street addresses
exist; shared perb_employer wiring is configured but not in default steps.

Companion leads (not this feed): Lexum/Norma decisions (CAPTCHA here), OCB
representation docket, NYS PERB (CBA already via ecommons-cba).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NYC OCB Bargaining Units Flow"
REPORT_PREFIX = "nyc_ocb_bargaining_units"
AGENCY_CODE = "NYC_OCB"
BASE_URL = "https://www.ocb-nyc.org"
LISTING_URL = f"{BASE_URL}/bargaining/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "certification_number",
    "canonical_case_type",
    "native_case_type",
    "bargaining_unit_name",
    "union_name",
    "dcas_cbu_number",
    "titles_pdf_url",
    "employer_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

def _normalize_certification_number(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def parse_bargaining_units_table(html: str, *, scraped_at: str) -> list[dict[str, str]]:
    """Parse the Certification# / Colloquial Name / Union / DCAS CBU# table."""
    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        certification_number = strip_html_text(cells[0])
        if not certification_number or "certification" in certification_number.lower():
            continue

        name_cell = cells[1]
        href_match = re.search(r'href="([^"]+)"', name_cell, flags=re.I)
        titles_pdf_url = _absolute_url(href_match.group(1)) if href_match else ""
        bargaining_unit_name = strip_html_text(name_cell)
        union_name = strip_html_text(cells[2])
        dcas_cbu_number = strip_html_text(cells[3])

        cert_key = _normalize_certification_number(certification_number)
        row_key = f"{AGENCY_CODE}:{cert_key}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "certification_number": certification_number,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "BOC_BARGAINING_UNIT",
                "bargaining_unit_name": bargaining_unit_name,
                "union_name": union_name,
                "dcas_cbu_number": dcas_cbu_number,
                "titles_pdf_url": titles_pdf_url,
                # ACE deferred — no per-unit street employer on the roster page.
                "employer_name": "",
                "jurisdiction_city": "",
                "jurisdiction_state": "NY",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": LISTING_URL,
                "source_url": titles_pdf_url or LISTING_URL,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_bargaining_units(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(LISTING_URL, delay_seconds=delay_seconds)
    rows = parse_bargaining_units_table(html, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"NYC OCB bargaining units page parsed 0 rows: {LISTING_URL}")
    rows.sort(key=lambda row: row["certification_number"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_bargaining_units(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

