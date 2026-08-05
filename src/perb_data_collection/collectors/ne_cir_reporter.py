"""Nebraska CIR Reporter decision index.

WHAT THIS FILE IS FOR
---------------------
Enumerate CIR Reporter volumes on nebraska.gov's reporter_and_appeals_search,
parse decision filenames for citation / year / party hints, and land a wide
index feed through shared state-PERB ACE (GeoCensus).

Most CIR matters are wage/interest disputes rather than pure certifications;
`canonical_case_type` defaults to ARBITRATION with filename heuristics for
representation-ish language. Cadence is monthly (volume archive).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NE CIR Reporter Flow"
REPORT_PREFIX = "ne_cir_reporter"
AGENCY_CODE = "NE_CIR"
BASE_URL = "https://www.nebraska.gov"
INDEX_URL = (
    f"{BASE_URL}/ncir/reporter_and_appeals_search/index.cgi?type=reporter"
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "cir_volume",
    "cir_page",
    "decision_year",
    "employer_name",
    "union_name",
    "document_title",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_VOLUME_RE = re.compile(
    r"index\.cgi\?dir=(\d+_CIR_xx)&type=reporter",
    flags=re.I,
)
_DECISION_HREF_RE = re.compile(
    r'href="([^"]*data/reporter/[^"]+\.html?)"',
    flags=re.I,
)
# 19_CIR_13_(2014)_NAPE_Local_61_NE_Dept._Corrections.htm
# 1_CIR_1_(1948).html
_FILENAME_RE = re.compile(
    r"^(?P<vol>\d+)_CIR_?(?P<page>\d+)__?\((?P<year>\d{4})\)(?:_(?P<rest>.+))?$",
    flags=re.I,
)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def list_volume_dirs(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for vol in _VOLUME_RE.findall(html):
        key = vol.upper()
        if key in seen:
            continue
        seen.add(key)
        found.append(vol)
    # Stable numeric order.
    found.sort(key=lambda v: int(v.split("_", 1)[0]))
    return found

def volume_index_url(volume_dir: str) -> str:
    return (
        f"{BASE_URL}/ncir/reporter_and_appeals_search/index.cgi"
        f"?dir={volume_dir}&type=reporter"
    )

def list_decision_hrefs(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for href in _DECISION_HREF_RE.findall(html):
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(href)
    found.sort(key=str.lower)
    return found

def _split_parties(rest: str) -> tuple[str, str]:
    """Heuristic: last '_v_' / '_City_of_' chunk tends to be employer side."""
    text = rest.replace("__", "_")
    text = re.sub(r"_+", " ", text).strip()
    text = text.replace(" Ass n", " Ass'n").replace(" Int l", " Int'l")
    lowered = text.lower()
    for sep in (" v ", " vs "):
        if sep in lowered:
            idx = lowered.rfind(sep)
            left = text[:idx].strip(" -_")
            right = text[idx + len(sep) :].strip(" -_")
            return right, left  # employer, union guess
    # "Union City of X" / "Union NE Dept ..." — employer often after city/dept cue
    for marker in (" City of ", " Co ", " County ", " Dept ", " Department ", " NE "):
        if marker.lower() in f" {lowered} ":
            # Prefer splitting at last " City of "
            pass
    city = re.search(
        r"(.+?)\s+(City of .+)$",
        text,
        flags=re.I,
    )
    if city:
        return city.group(2).strip(), city.group(1).strip()
    # Fallback: put full string as employer label for ACE city/state geocode of NE
    return text, ""

def _canonical_from_title(title: str) -> str:
    lowered = title.lower()
    if "decertif" in lowered:
        return "DECERTIFICATION"
    if any(k in lowered for k in ("certif", "represent", "election", "bargaining unit")):
        return "CERTIFICATION"
    return "ARBITRATION"

def parse_decision_filename(
    href: str,
    *,
    volume_dir: str,
    volume_page_url: str,
    scraped_at: str,
) -> dict[str, str] | None:
    name = unquote(href.rsplit("/", 1)[-1])
    stem = re.sub(r"\.html?$", "", name, flags=re.I)
    match = _FILENAME_RE.match(stem)
    if not match:
        # Still land a row with raw filename.
        case_number = stem.replace("_", " ")
        return {
            "row_key": f"{AGENCY_CODE}:{stem[:120]}",
            "source_agency_code": AGENCY_CODE,
            "case_number": case_number[:80],
            "canonical_case_type": "ARBITRATION",
            "native_case_type": "CIR_REPORTER",
            "cir_volume": volume_dir.split("_", 1)[0],
            "cir_page": "",
            "decision_year": "",
            "employer_name": case_number,
            "union_name": "",
            "document_title": stem,
            "jurisdiction_city": "",
            "jurisdiction_state": "NE",
            "employer_street": "",
            "employer_zip": "",
            "source_page_url": volume_page_url,
            "source_url": _absolute_url(href),
            "scraped_at": scraped_at,
        }

    vol = match.group("vol")
    page = match.group("page")
    year = match.group("year")
    rest = match.group("rest") or ""
    employer, union = _split_parties(rest) if rest else ("", "")
    if not employer and not union:
        employer = f"CIR Volume {vol} p.{page}"
    case_number = f"{vol} CIR {page} ({year})"
    title = unquote(stem)
    return {
        "row_key": f"{AGENCY_CODE}:{vol}_CIR_{page}_{year}",
        "source_agency_code": AGENCY_CODE,
        "case_number": case_number,
        "canonical_case_type": _canonical_from_title(title),
        "native_case_type": "CIR_REPORTER",
        "cir_volume": vol,
        "cir_page": page,
        "decision_year": year,
        "employer_name": employer,
        "union_name": union,
        "document_title": title,
        "jurisdiction_city": "",
        "jurisdiction_state": "NE",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": volume_page_url,
        "source_url": _absolute_url(href),
        "scraped_at": scraped_at,
    }

def scrape_reporter(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    index_html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    volumes = list_volume_dirs(index_html)
    if not volumes:
        raise RuntimeError(f"NE CIR reporter index found 0 volumes: {INDEX_URL}")

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for volume_dir in volumes:
        page_url = volume_index_url(volume_dir)
        vol_html = fetcher(page_url, delay_seconds=delay_seconds)
        for href in list_decision_hrefs(vol_html):
            parsed = parse_decision_filename(
                href,
                volume_dir=volume_dir,
                volume_page_url=page_url,
                scraped_at=scraped_at,
            )
            if parsed is None:
                continue
            if parsed["row_key"] in seen_keys:
                continue
            seen_keys.add(parsed["row_key"])
            rows.append(parsed)

    if not rows:
        raise RuntimeError("NE CIR reporter volumes parsed 0 decisions")
    rows.sort(key=lambda row: (row["cir_volume"].zfill(3), row["cir_page"].zfill(5)))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_reporter(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

