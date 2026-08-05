"""Delaware PERB year-indexed decision PDFs.

WHAT THIS FILE IS FOR
---------------------
Walk perb.delaware.gov year decision pages (1984–present), collect each
decision PDF link + anchor title, map ULP/REP/clarification language into the
shared canonical case-type enum, then write a wide CSV.

Party / employer hints come from filename `-v-` splits and title text.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "DE PERB Decisions Flow"
REPORT_PREFIX = "de_perb_decisions"
AGENCY_CODE = "DE_PERB"
BASE_URL = "https://perb.delaware.gov"
INDEX_URL = f"{BASE_URL}/decisions/"

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

_YEAR_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>\s*((?:19|20)\d{2})\s*<',
    flags=re.I,
)
_PDF_ANCHOR_RE = re.compile(
    r'<a[^>]+href="([^"]+\.pdf[^"]*)"[^>]*>(.*?)</a>',
    flags=re.I | re.S,
)
_TITLE_RE = re.compile(
    r"View decision\s+"
    r"(?:(?P<year>(?:19|20)\d{2})\s+)?"
    r"(?:(?P<kind>ULP|REP)\s+)?"
    r"(?P<case>\d+[A-Z]?)\s+"
    r"(?P<desc>.+)$",
    flags=re.I,
)
_CASE_FROM_FILE_RE = re.compile(
    r"^(?:ULP-)?(?P<case>\d+[A-Z]?)\b",
    flags=re.I,
)

def _absolute_url(href: str, base: str = BASE_URL) -> str:
    return urljoin(base.rstrip("/") + "/", href)

def list_year_pages(html: str) -> list[tuple[str, str]]:
    """Return unique (year, absolute_url) pairs, newest first."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, year in _YEAR_LINK_RE.findall(html):
        if year in seen:
            continue
        seen.add(year)
        found.append((year, _absolute_url(href, INDEX_URL)))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return found

def _canonical(native_kind: str, title: str) -> str:
    lowered = f"{native_kind} {title}".lower()
    if "decertif" in lowered:
        return "DECERTIFICATION"
    if "clarif" in lowered:
        return "UNIT_CLARIFICATION"
    if "appropriateness" in lowered or "unit determination" in lowered:
        return "UNIT_MODIFICATION"
    if "supervisory" in lowered and "rep" in lowered:
        return "UNIT_CLARIFICATION"
    if native_kind.upper() == "ULP" or "ulp" in lowered:
        return "ULP"
    if native_kind.upper() == "REP" or "recognition" in lowered or "election" in lowered:
        return "CERTIFICATION"
    if "probable cause" in lowered:
        return "ULP"
    return "ULP" if "ulp" in title.lower() else "CERTIFICATION"

def _parties_from_filename(filename: str) -> tuple[str, str]:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    stem = re.sub(r"-website$", "", stem, flags=re.I)
    stem = stem.replace(".", " ")
    # Prefer last -v- / -v.- split
    match = re.search(r"^(?P<left>.+?)-v[.-](?P<right>.+)$", stem, flags=re.I)
    if not match:
        return "", ""
    left = re.sub(r"[-_]+", " ", match.group("left")).strip()
    right = re.sub(r"[-_]+", " ", match.group("right")).strip()
    # Drop leading case # / doc-type tokens from left
    left = re.sub(
        r"^(?:\d+[A-Z]?\s+)?(?:ULP\s+)?(?:PCD|Dec|OOD|CLAR|Bd Decision on Review|"
        r"Order of Dismissal|Decision on the Merits|Appropriateness Determination)\s+",
        "",
        left,
        flags=re.I,
    ).strip()
    left = re.sub(
        r"^(?:PCD|ULP|CLAR|Dec|OOD|Bd)\s+",
        "",
        left,
        flags=re.I,
    ).strip()
    # Date tails on right like "1 29 26"
    right = re.sub(r"\s+\d{1,2}\s+\d{1,2}\s+\d{2,4}$", "", right).strip()
    return right, left  # employer, union

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(r"^(City|Town|County)\s+of\s+", "", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

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
        if pdf_url.lower() in seen:
            continue
        seen.add(pdf_url.lower())
        title = strip_html_text(raw_label)
        title = re.sub(r"^View decision\s+", "View decision ", title, flags=re.I)
        filename = unquote(pdf_url.rsplit("/", 1)[-1])

        year = decision_year
        kind = ""
        case_number = ""
        desc = title
        match = _TITLE_RE.match(title)
        if match:
            year = match.group("year") or decision_year
            kind = (match.group("kind") or "").upper()
            case_number = match.group("case")
            desc = match.group("desc").strip()
        if not case_number:
            file_match = _CASE_FROM_FILE_RE.match(filename)
            if file_match:
                case_number = file_match.group("case")
        if not case_number:
            case_number = re.sub(r"[^A-Za-z0-9]+", "-", filename)[:40]

        employer, union = _parties_from_filename(filename)
        if not employer:
            employer = desc[:120]
        native = kind or (
            "ULP"
            if "ulp" in title.lower()
            else "REP"
            if "rep" in title.lower()
            else "DECISION"
        )
        row_key = f"{AGENCY_CODE}:{year}:{case_number}:{filename[:60]}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": _canonical(native, title),
                "native_case_type": native,
                "decision_year": year,
                "employer_name": employer,
                "union_name": union,
                "document_title": desc or title,
                "pdf_url": pdf_url,
                "jurisdiction_city": _jurisdiction_city(employer),
                "jurisdiction_state": "DE",
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
    index_html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    years = list_year_pages(index_html)
    if not years:
        raise RuntimeError(f"DE PERB decisions index found 0 year pages: {INDEX_URL}")

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
        raise RuntimeError("DE PERB year pages parsed 0 decision PDFs")
    rows.sort(key=lambda row: (row["decision_year"], row["case_number"], row["pdf_url"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_decisions(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

