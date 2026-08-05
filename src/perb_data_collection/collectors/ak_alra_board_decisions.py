"""Alaska ALRA board decision PDF index.

WHAT THIS FILE IS FOR
---------------------
labor.alaska.gov hosts a single HTML index of ALRA Decision & Order PDFs.
Anchor text is typically the case number (e.g. 17-1708-ULP, 15-1666-RC).
Walk that index, map RC/UC/ULP/… suffixes into the shared canonical_case_type
enum, and land rows through shared state-PERB ACE (GeoCensus).

Addresses are not published on the index — jurisdiction is AK with city blank;
ACE geocodes on state alone when needed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "AK ALRA Board Decisions Flow"
REPORT_PREFIX = "ak_alra_board_decisions"
AGENCY_CODE = "AK_ALRA"
BASE_URL = "https://labor.alaska.gov"
INDEX_URL = f"{BASE_URL}/laborr/do/alra-board-decisions-and-orders.html"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "decision_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
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

_PDF_ANCHOR_RE = re.compile(
    r'<a[^>]+href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>',
    flags=re.I | re.S,
)
# 17-1708-ULP / 12-1265CBA / UCF 90-3 / SLA 4292.0001
_CASE_RE = re.compile(
    r"^(?P<case>\d{2}-\d{3,4}(?:[A-Z])?(?:-(?P<suffix>[A-Z]{2,4}))?|"
    r"\d{2}-\d{3,4}(?P<suffix2>CBA|ULP|UC|RC|RD)|"
    r"UCF\s+\d+-\d+|SLA\s+[\d.]+|[A-Z]{2,5}\s+\d[\w.-]*)\s*$",
    flags=re.I,
)
_SUFFIX_CANONICAL = {
    "RC": "CERTIFICATION",
    "RD": "DECERTIFICATION",
    "UC": "UNIT_CLARIFICATION",
    "ULP": "ULP",
    "CBA": "ARBITRATION",
    "CE": "CERTIFICATION",
}

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _native_suffix(case_number: str) -> str:
    match = re.search(r"-(RC|UC|ULP|CBA|RD|CE)\b", case_number, flags=re.I)
    if match:
        return match.group(1).upper()
    match = re.search(r"(RC|UC|ULP|CBA|RD)\s*$", case_number, flags=re.I)
    if match:
        return match.group(1).upper()
    if case_number.upper().startswith("UCF"):
        return "UC"
    return "DECISION"

def _canonical(native: str) -> str:
    return _SUFFIX_CANONICAL.get(native.upper(), "ULP" if native == "DECISION" else "CERTIFICATION")

def _decision_number_from_filename(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    if re.fullmatch(r"\d+", stem):
        return stem
    return stem[:40]

def parse_decisions_page(
    html: str,
    *,
    page_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, raw_label in _PDF_ANCHOR_RE.findall(html):
        pdf_url = _absolute_url(href)
        key = pdf_url.lower()
        if key in seen:
            continue
        seen.add(key)
        title = strip_html_text(raw_label)
        filename = href.rsplit("/", 1)[-1]
        decision_number = _decision_number_from_filename(filename)
        case_number = title.strip() or f"DO-{decision_number}"
        native = _native_suffix(case_number)
        row_key = f"{AGENCY_CODE}:{decision_number}:{case_number[:60]}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "decision_number": decision_number,
                "canonical_case_type": _canonical(native),
                "native_case_type": native,
                "employer_name": "",
                "union_name": "",
                "document_title": case_number,
                "pdf_url": pdf_url,
                "jurisdiction_city": "",
                "jurisdiction_state": "AK",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": page_url,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_decisions(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    rows = parse_decisions_page(html, page_url=INDEX_URL, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"AK ALRA board decisions index found 0 PDFs: {INDEX_URL}")
    rows.sort(key=lambda row: (row["decision_number"].zfill(6), row["case_number"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_decisions(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

