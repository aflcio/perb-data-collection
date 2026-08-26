"""Rhode Island RISLRB certification tables → employer ACE (GeoCensus) → Redshift (clrr)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "RISLRB Certifications Flow"
REPORT_PREFIX = "rislrb_certifications"
AGENCY_CODE = "RI_RISLRB"
BASE_URL = "http://rislrb.ri.gov/"

CERTIFICATION_PAGES: tuple[tuple[str, str], ...] = (
    ("Firefighters", "FireFighterCert.htm"),
    ("Police Officers", "PoliceCert.htm"),
    ("Certified Teachers", "TeacherCert.htm"),
    ("Municipal City and Town", "CityTownMuniCert.htm"),
    ("Municipal Non-Professional School", "NonProfMuniCert.htm"),
    ("Municipal Authorities", "AuthorityMuniCert.htm"),
    ("State and Quasi-State", "StateQuasiCert.htm"),
    ("Miscellaneous", "MiscCert.htm"),
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "certification_category",
    "employer_name",
    "union_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "date_certified",
    "date_amended",
    "certification_pdf_url",
    "disposition_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

def _normalize_case_number(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())

def _extract_dates(date_cell: str) -> tuple[str, str]:
    primary = ""
    amended = ""
    for match in re.finditer(r"\(?\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*\)?", date_cell):
        token = match.group(1)
        if match.group(0).strip().startswith("("):
            amended = token
        elif not primary:
            primary = token
    if not primary and amended:
        primary = amended
        amended = ""
    return primary, amended

def _parse_certification_table(
    html: str,
    *,
    category: str,
    page_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    table_match = re.search(
        r'<table[^>]*class="sortable"[^>]*>(.*)',
        html,
        flags=re.I | re.S,
    )
    if not table_match:
        return []

    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 5:
            continue
        case_number = strip_html_text(cells[1])
        if not re.match(r"EE-\d+", case_number, flags=re.I):
            continue

        employer_cell = cells[0]
        cert_href = re.search(r'href="([^"]+)"', employer_cell, flags=re.I)
        cert_pdf = urljoin(page_url, cert_href.group(1)) if cert_href else ""
        # Employer text lives inside the <a> (and sometimes after it). Taking only
        # post-</a> text left many cells empty, and the old fallback wrote the raw
        # href="…" attribute into employer_name (infra-36). Never use the href as
        # a display value.
        employer_name = strip_html_text(employer_cell)

        union_name = strip_html_text(cells[2])
        date_certified, date_amended = _extract_dates(strip_html_text(cells[3]))

        disposition_cell = cells[4]
        disp_href = re.search(r'href="([^"]+)"', disposition_cell, flags=re.I)
        disposition_pdf = urljoin(page_url, disp_href.group(1)) if disp_href else ""

        case_key = _normalize_case_number(case_number)
        canonical = "UNIT_CLARIFICATION" if disposition_pdf else "CERTIFICATION"
        row_key = f"{AGENCY_CODE}:{case_key}:{category}"

        # Listing pages do not state a reliable city; deriving city from
        # employer_name leaked href= markup and unit descriptors into ACE.
        jurisdiction_city = ""
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_key,
                "canonical_case_type": canonical,
                "native_case_type": "CERTIFICATION",
                "certification_category": category,
                "employer_name": employer_name,
                "union_name": union_name,
                "jurisdiction_city": jurisdiction_city,
                "jurisdiction_state": "RI",
                "employer_street": "",
                "employer_zip": "",
                "date_certified": date_certified,
                "date_amended": date_amended,
                "certification_pdf_url": cert_pdf,
                "disposition_pdf_url": disposition_pdf,
                "source_page_url": page_url,
                "source_url": cert_pdf or page_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    """Scrape all RISLRB certification category tables."""
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    all_rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for category, page_name in CERTIFICATION_PAGES:
        page_url = urljoin(BASE_URL, page_name)
        html = fetcher(page_url, delay_seconds=delay_seconds)
        for row in _parse_certification_table(
            html,
            category=category,
            page_url=page_url,
            scraped_at=scraped_at,
        ):
            if row["row_key"] in seen_keys:
                continue
            seen_keys.add(row["row_key"])
            all_rows.append(row)

    all_rows.sort(key=lambda row: (row["case_number"], row["certification_category"]))
    return all_rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

