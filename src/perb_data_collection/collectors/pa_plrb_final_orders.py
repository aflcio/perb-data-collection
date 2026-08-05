"""Pennsylvania PLRB Final Orders.

WHAT THIS FILE IS FOR
---------------------
PA.gov publishes PLRB Final Orders as year-indexed HTML lists with PDF links
(Union v. Employer titles). Walk the index → each year page, recover case
numbers from PERA/PF/PLRA-style filename tokens, then run shared state-PERB
ACE (GeoCensus) on employer jurisdiction hints.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

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
    parts = _V_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    left, right = parts[0].strip(), parts[1].strip()
    # Typical: Union v. Employer
    return right[:160], left[:160]

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
    for href, raw_label in _PDF_ANCHOR_RE.findall(html):
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
        filename = unquote(pdf_url.rsplit("/", 1)[-1])
        case_number = _case_from_filename(filename)
        employer, union = _parties_from_title(title)
        native = case_number.split("-")[0] if "-" in case_number else "ORDER"
        row_key = f"{AGENCY_CODE}:{decision_year}:{case_number}:{filename[:50]}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": _canonical(title, case_number),
                "native_case_type": native,
                "decision_year": decision_year,
                "employer_name": employer or title[:120],
                "union_name": union,
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

def scrape_orders(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
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
    rows.sort(key=lambda row: (row["decision_year"], row["case_number"], row["pdf_url"]), reverse=True)
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_orders(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

