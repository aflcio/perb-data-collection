"""Maryland laborboards election certifications → employer ACE (GeoCensus) → Redshift."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "MD PERB Election Certifications Flow"
REPORT_PREFIX = "md_perb_election_certs"
AGENCY_CODE = "MD_PERB"
BASE_URL = "https://laborboard.maryland.gov"
LISTING_URL = f"{BASE_URL}/decisions/election-certifications"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "employer_type",
    "employer_name",
    "union_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "event_date",
    "document_title",
    "document_description",
    "pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_CASE_NUMBER_RE = re.compile(
    r"\b((?:PERB|SLRB|PSLRB|SHELRB)\s+[A-Z]{1,3}\.?[A-Z]?\s*\d{4}-\d+)\b",
    flags=re.I,
)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)

def _parse_case_number(title: str) -> str:
    match = _CASE_NUMBER_RE.search(title)
    if match:
        return re.sub(r"\s+", " ", match.group(1).strip().upper())
    return ""

def _parse_employer_union(title: str) -> tuple[str, str]:
    cleaned = strip_html_text(title)
    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        return left.strip(), right.strip()
    if "," in cleaned:
        parts = [part.strip() for part in cleaned.split(",") if part.strip()]
        if len(parts) >= 2:
            return parts[0], ", ".join(parts[1:])
    return cleaned, ""

def _parse_listing_items(html: str, *, scraped_at: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for article in re.findall(
        r'<article class="maryland-listing-item__container"[^>]*>(.*?)</article>',
        html,
        flags=re.I | re.S,
    ):
        eyebrow_match = re.search(
            r'maryland-listing-item__eyebrow[^>]*>\s*([^<]+?)\s*</div>',
            article,
            flags=re.I | re.S,
        )
        employer_type = strip_html_text(eyebrow_match.group(1)) if eyebrow_match else ""

        title_match = re.search(
            r'maryland-link__document-title">([^<]+)</span>',
            article,
            flags=re.I,
        )
        title = strip_html_text(title_match.group(1)) if title_match else ""

        href_match = re.search(
            r'<a class="maryland-listing-item__title" href="([^"]+)"',
            article,
            flags=re.I,
        )
        detail_href = _absolute_url(href_match.group(1)) if href_match else LISTING_URL
        pdf_url = detail_href if detail_href.lower().endswith(".pdf") else detail_href

        date_match = re.search(
            r'maryland-listing-item__date[^>]*>\s*([^<]+?)\s*</div>',
            article,
            flags=re.I | re.S,
        )
        event_date = strip_html_text(date_match.group(1)) if date_match else ""

        desc_match = re.search(
            r'maryland-listing-item__description[^>]*>\s*<p>([^<]*)</p>',
            article,
            flags=re.I | re.S,
        )
        description = strip_html_text(desc_match.group(1)) if desc_match else ""

        case_number = _parse_case_number(title)
        employer_name, union_name = _parse_employer_union(
            title.split(" - ", 1)[-1] if case_number and " - " in title else title
        )
        if case_number and title.upper().startswith(case_number.split()[0]):
            remainder = title[len(case_number) :].lstrip(" ,-")
            employer_name, union_name = _parse_employer_union(remainder)

        media_id = re.search(r"/media/(\d+)", detail_href)
        row_key = f"{AGENCY_CODE}:{media_id.group(1)}" if media_id else f"{AGENCY_CODE}:{case_number or title}"

        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "Election Certifications",
                "employer_type": employer_type,
                "employer_name": employer_name,
                "union_name": union_name,
                "jurisdiction_city": "",
                "jurisdiction_state": "MD",
                "employer_street": "",
                "employer_zip": "",
                "event_date": event_date,
                "document_title": title,
                "document_description": description,
                "pdf_url": pdf_url,
                "source_page_url": LISTING_URL,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_election_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(LISTING_URL, delay_seconds=delay_seconds)
    rows = _parse_listing_items(html, scraped_at=scraped_at)
    total_match = re.search(
        r"Displaying\s+\d+\s*[-–]\s*\d+\s+of\s+(\d+)\s+results",
        html,
        flags=re.I,
    )
    if total_match:
        reported_total = int(total_match.group(1))
        if reported_total != len(rows):
            raise RuntimeError(
                f"MD election cert listing report {reported_total} results but "
                f"parsed {len(rows)} articles — listing may be truncated or markup changed"
            )
    rows.sort(key=lambda row: row["row_key"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_election_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

