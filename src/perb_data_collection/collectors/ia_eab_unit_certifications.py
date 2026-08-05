"""Iowa EAB public unit-certification listings.

WHAT THIS FILE IS FOR
---------------------
SuPERB's Blazor document search is broken from this host. The Employment Appeal
Board instead publishes unit-certification PDFs as paginated Drupal teasers under
six employer-type paths (cities, counties, K-12, AEAs, CCs, state).

Analogous to ME MLRB's HTML index: the listing title already carries employer,
union, and an optional unit parenthetical. Linked PDFs are mostly image scans, so
this flow lands wide staging from listing metadata only (media id = stable key),
then runs shared state-PERB ACE (GeoCensus) on Iowa city + state.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "IA EAB Unit Certifications Flow"
REPORT_PREFIX = "ia_eab_unit_certifications"
AGENCY_CODE = "IA_EAB"
BASE_URL = "https://eab.iowa.gov"
HUB_URL = f"{BASE_URL}/public-collective-bargaining/unit-certifications"

# Path → employer_type label stored on wide rows.
LISTING_SECTIONS: tuple[tuple[str, str], ...] = (
    ("/cities", "cities"),
    ("/counties", "counties"),
    ("/k-12-schools", "k12_schools"),
    ("/area-education-agencies-aeas", "area_education_agencies"),
    ("/community-colleges-ccs", "community_colleges"),
    ("/state", "state"),
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "media_id",
    "canonical_case_type",
    "native_case_type",
    "employer_type",
    "employer_name",
    "union_name",
    "bargaining_unit_name",
    "document_title",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_TOTAL_RE = re.compile(
    r"Displaying\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+results",
    flags=re.I,
)
_ITEM_RE = re.compile(
    r'<a[^>]+href="(/media/(\d+)/download(?:\?inline)?)"[^>]*>'
    r".*?<h2>\s*(.*?)\s*</h2>",
    flags=re.I | re.S,
)
_PAGESIZE = 20

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def listing_total(html: str) -> int:
    match = _TOTAL_RE.search(html)
    if not match:
        raise RuntimeError("Iowa EAB listing missing 'Displaying N - M of T results'")
    return int(match.group(1))

def parse_listing_items(html: str) -> list[tuple[str, str, str]]:
    """Return [(media_id, pdf_path, raw_title), ...] from one listing page."""
    items: list[tuple[str, str, str]] = []
    for match in _ITEM_RE.finditer(html):
        pdf_path = match.group(1)
        media_id = match.group(2)
        title = strip_html_text(match.group(3))
        title = re.sub(r"\.pdf\s*$", "", title, flags=re.I).strip()
        if not title:
            continue
        items.append((media_id, pdf_path, title))
    return items

def _parties_from_title(title: str) -> tuple[str, str, str]:
    """Split '{Employer} and {Union} ({Unit})' listing titles."""
    cleaned = re.sub(r"\.pdf\s*$", "", title.strip(), flags=re.I).strip()
    unit = ""
    paren = re.search(r"\(([^)]+)\)\s*$", cleaned)
    if paren:
        unit = paren.group(1).strip()
        cleaned = cleaned[: paren.start()].strip()

    if " and " in cleaned:
        employer, union = cleaned.split(" and ", 1)
        return employer.strip(), union.strip(), unit
    return cleaned, "", unit

def _jurisdiction_city(employer_name: str, *, employer_type: str) -> str:
    name = employer_name.strip()
    if not name:
        return ""
    if employer_type == "state":
        return "Des Moines"
    name = re.sub(r"^(City|Town|Village)\s+of\s+", "", name, flags=re.I)
    name = re.sub(r"\s+County(\s+.*)?$", " County", name, flags=re.I)
    # "Adel" / "Akron" / school district names — first clause before comma.
    return name.split(",")[0].strip()[:80]

def parse_listing_title(
    *,
    media_id: str,
    title: str,
    pdf_url: str,
    listing_url: str,
    employer_type: str,
    scraped_at: str,
) -> dict[str, str]:
    clean_title = re.sub(r"\.pdf\s*$", "", title.strip(), flags=re.I).strip()
    employer_name, union_name, bargaining_unit = _parties_from_title(clean_title)
    return {
        "row_key": f"{AGENCY_CODE}:{media_id}",
        "source_agency_code": AGENCY_CODE,
        "media_id": media_id,
        "canonical_case_type": "CERTIFICATION",
        "native_case_type": "UNIT_CERTIFICATION",
        "employer_type": employer_type,
        "employer_name": employer_name,
        "union_name": union_name,
        "bargaining_unit_name": bargaining_unit,
        "document_title": clean_title,
        "jurisdiction_city": _jurisdiction_city(
            employer_name, employer_type=employer_type
        ),
        "jurisdiction_state": "IA",
        "employer_street": "",
        "employer_zip": "",
        "pdf_url": pdf_url,
        "source_page_url": listing_url,
        "source_url": pdf_url,
        "scraped_at": scraped_at,
    }

def scrape_section(
    path: str,
    employer_type: str,
    *,
    delay_seconds: float,
    fetch_html: Any,
    scraped_at: str,
) -> tuple[list[dict[str, str]], int]:
    """Scrape one employer-type listing; return (rows, reported_total)."""
    listing_url = _absolute_url(path.lstrip("/"))
    first_html = fetch_html(listing_url, delay_seconds=delay_seconds)
    total = listing_total(first_html)
    page_count = max(1, math.ceil(total / _PAGESIZE))

    rows: list[dict[str, str]] = []
    seen_media: set[str] = set()

    for page in range(page_count):
        html = (
            first_html
            if page == 0
            else fetch_html(f"{listing_url}?page={page}", delay_seconds=delay_seconds)
        )
        for media_id, pdf_path, title in parse_listing_items(html):
            if media_id in seen_media:
                continue
            seen_media.add(media_id)
            pdf_url = _absolute_url(pdf_path)
            rows.append(
                parse_listing_title(
                    media_id=media_id,
                    title=title,
                    pdf_url=pdf_url,
                    listing_url=listing_url,
                    employer_type=employer_type,
                    scraped_at=scraped_at,
                )
            )

    if total and abs(len(rows) - total) > max(2, total // 50):
        raise RuntimeError(
            f"Iowa EAB {path}: expected ~{total} rows, scraped {len(rows)}"
        )
    return rows, total

def scrape_unit_certifications(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    sections: tuple[tuple[str, str], ...] | None = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    selected = sections or LISTING_SECTIONS

    all_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    reported_total = 0

    for path, employer_type in selected:
        section_rows, section_total = scrape_section(
            path,
            employer_type,
            delay_seconds=delay_seconds,
            fetch_html=fetcher,
            scraped_at=scraped_at,
        )
        reported_total += section_total
        for row in section_rows:
            if row["media_id"] in seen:
                continue
            seen.add(row["media_id"])
            all_rows.append(row)

    if not all_rows:
        raise RuntimeError(f"Iowa EAB unit certifications scraped 0 rows from {HUB_URL}")

    all_rows.sort(key=lambda row: (row["employer_type"], int(row["media_id"])))
    return all_rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_unit_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

