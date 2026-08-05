"""Wisconsin WERC annual certification election results.

WHAT THIS FILE IS FOR
---------------------
Scrape WERC's Election Results page for Spring/Fall annual recertification PDF
tallies, extract one row per bargaining unit, then run the shared state-PERB
ACE (GeoCensus) path into Redshift.

Source: https://werc.wi.gov/representation-election-updates/
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, fetch_bytes
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "WERC Election Results Flow"
REPORT_PREFIX = "werc_election_results"
AGENCY_CODE = "WI_WERC"
BASE_URL = "https://werc.wi.gov"
LISTING_URL = f"{BASE_URL}/representation-election-updates/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "unit_code",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "bargaining_unit_name",
    "unit_population",
    "votes_cast",
    "votes_yes",
    "votes_no",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "election_cycle",
    "source_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_PDF_HREF_RE = re.compile(
    r'href="([^"]+\.pdf[^"]*)"',
    flags=re.I,
)
_RESULT_NAME_RE = re.compile(
    r"(election|result|votes?_cast|endpoint|finalresults|recert)",
    flags=re.I,
)
_CYCLE_RE = re.compile(
    r"(?P<season>spring|fall|apr(?:il)?|nov(?:ember)?).*?(?P<year>20\d{2})"
    r"|(?P<year2>20\d{2}).*?(?P<season2>spring|fall|apr(?:il)?|nov(?:ember)?)",
    flags=re.I,
)
_ROW_RE = re.compile(
    r"^\s*(?P<code>\d{1,3}\.\d{3,4})\s+"
    r"(?P<employer>.+?)\s{2,}"
    r"(?P<union>.+?)\s{2,}"
    r"(?P<unit>.+?)\s{2,}"
    r"(?P<pop>\d+)\s+"
    r"(?P<votes>\d+)\s+"
    r"(?P<yes>\d+)\s+"
    r"(?P<no>\d+)\s*$"
)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _election_cycle_from_url(url: str) -> str:
    name = Path(url).name
    match = _CYCLE_RE.search(name.replace("_", " ").replace("-", " "))
    if not match:
        return name
    season = (match.group("season") or match.group("season2") or "").lower()
    year = match.group("year") or match.group("year2") or ""
    if season.startswith("apr"):
        season = "spring"
    if season.startswith("nov"):
        season = "fall"
    return f"{season}_{year}" if season and year else name

def _jurisdiction_city(employer_name: str) -> str:
    # "Altoona/City of" / "Milwaukee County" / "Madison/City of"
    if "/" in employer_name:
        return employer_name.split("/", 1)[0].strip()
    return employer_name.split(",")[0].strip()

def _list_result_pdf_urls(html: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for href in _PDF_HREF_RE.findall(html):
        url = _absolute_url(href)
        if not _RESULT_NAME_RE.search(url):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(url)
    return urls

def _pdf_to_text(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(pdf_bytes)
        handle.flush()
        try:
            completed = subprocess.run(
                ["pdftotext", "-layout", handle.name, "-"],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pdftotext is required to parse WERC election result PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftotext failed: {exc.stderr or exc.stdout or exc}"
            ) from exc
        return completed.stdout

def _parse_result_text(
    text: str,
    *,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    cycle = _election_cycle_from_url(pdf_url)
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _ROW_RE.match(line)
        if not match:
            continue
        unit_code = match.group("code").strip()
        employer_name = re.sub(r"\s+", " ", match.group("employer")).strip()
        union_name = re.sub(r"\s+", " ", match.group("union")).strip()
        unit_name = re.sub(r"\s+", " ", match.group("unit")).strip()
        row_key = f"{AGENCY_CODE}:{cycle}:{unit_code}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "unit_code": unit_code,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "ANNUAL_CERTIFICATION_ELECTION",
                "employer_name": employer_name,
                "union_name": union_name,
                "bargaining_unit_name": unit_name,
                "unit_population": match.group("pop"),
                "votes_cast": match.group("votes"),
                "votes_yes": match.group("yes"),
                "votes_no": match.group("no"),
                "jurisdiction_city": _jurisdiction_city(employer_name),
                "jurisdiction_state": "WI",
                "employer_street": "",
                "employer_zip": "",
                "election_cycle": cycle,
                "source_pdf_url": pdf_url,
                "source_page_url": LISTING_URL,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_election_results(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    fetch_pdf: Any = None,
) -> list[dict[str, str]]:
    html_fetcher = fetch_html or fetch_url
    pdf_fetcher = fetch_pdf or fetch_bytes
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = html_fetcher(LISTING_URL, delay_seconds=delay_seconds)
    pdf_urls = _list_result_pdf_urls(html)
    if not pdf_urls:
        raise RuntimeError(f"No WERC election-result PDFs found on {LISTING_URL}")

    rows: list[dict[str, str]] = []
    for pdf_url in pdf_urls:
        pdf_bytes = pdf_fetcher(pdf_url, delay_seconds=delay_seconds)
        text = _pdf_to_text(pdf_bytes)
        parsed = _parse_result_text(text, pdf_url=pdf_url, scraped_at=scraped_at)
        rows.extend(parsed)

    if not rows:
        raise RuntimeError("WERC election PDFs parsed to 0 unit rows")

    rows.sort(key=lambda row: (row["election_cycle"], row["unit_code"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_election_results(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

