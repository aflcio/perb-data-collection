"""Wisconsin WERC annual certification election results.

WHAT THIS FILE IS FOR
---------------------
Scrape WERC's Election Results page for Spring/Fall annual recertification PDF
tallies, extract one row per bargaining unit, then run the shared state-PERB
ACE (GeoCensus) path into Redshift.

These PDFs are TALLIES, not results. WERC lists each one as "Endpoint ballots
cast in ... recertification elections", and each is headed "VOTES CAST AS OF
<time> ..." with a note that the parties then have eight days to file
challenges or objections. The Commission's certification (or its
decertification) comes afterwards and is not in these files. So every row here
is ``document_status = endpoint_tally``: the eligible population, the ballots,
yes and no, the challenged columns, and whether the yes votes reach the Act 10
threshold (51% of the unit, not of the ballots cast) are kept as separate
facts. None of them is a certification. Town of Bennett's IUOE Local 139 unit
in spring 2026 (2 eligible, 0 cast) is a tally that fails the threshold, not a
recertified union.

Rows are parsed from the right: the last numeric block holds four tally
columns and up to two challenged columns. The old parser took the last four
integers, so once the challenged columns were filled (fall 2025) every number
slid: Beaver Dam's teacher unit (253 eligible, 219 cast, 218 yes, 1 no, 1 and
1 challenged) read as 218 eligible and 1 vote cast.

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
    "challenged_unit_population",
    "challenged_votes",
    "meets_51pct_threshold",
    "document_status",
    "tally_as_of",
    "election_open_date",
    "election_close_date",
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
# A unit row starts with its code; the tally is the trailing block of 4-6
# integers, set off from the unit name by at least two spaces (-layout text).
_ROW_START_RE = re.compile(r"^\s*(?P<code>\d{1,3}\.\d{3,4})\s+(?P<rest>.*\S)\s*$")
_NUMERIC_TAIL_RE = re.compile(r"\s{2,}(?P<nums>\d+(?:\s+\d+){3,5})\s*$")
_HEADING_AS_OF_RE = re.compile(
    r"VOTES\s+CAST\s+AS\s+OF\s+(?P<as_of>[^\n]*?)\s+IN\s+ANNUAL", flags=re.I
)
_HEADING_WINDOW_RE = re.compile(
    r"CONDUCTED\s+(?P<open>\d{1,2}/\d{1,2}/\d{4})\s+THROUGH\s+(?P<close>\d{1,2}/\d{1,2}/\d{4})",
    flags=re.I,
)
ENDPOINT_TALLY = "endpoint_tally"

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

def _iso_mdy(value: str) -> str:
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return ""


def _challenged_columns(text: str) -> list[int]:
    """x-positions of the two "Challenged" header columns, left to right."""
    positions: list[int] = []
    for line in text.splitlines()[:40]:
        if _ROW_START_RE.match(line):
            break
        positions.extend(m.start() for m in re.finditer(r"Challenged", line))
    return sorted(set(positions))


def parse_tally_line(line: str, *, challenged_x: list[int] | None = None) -> dict[str, str] | None:
    """One unit row into its separate facts, or None when the line is not a row."""
    start = _ROW_START_RE.match(line)
    if not start:
        return None
    tail = _NUMERIC_TAIL_RE.search(line)
    if not tail:
        return None
    numbers = [(m.group(0), tail.start("nums") + m.start()) for m in re.finditer(r"\d+", tail.group("nums"))]
    text_part = line[start.start("rest") : tail.start()].strip()
    parts = [p.strip() for p in re.split(r"\s{2,}", text_part) if p.strip()]
    employer = parts[0] if parts else ""
    union = parts[1] if len(parts) > 1 else ""
    unit = " ".join(parts[2:])
    pop, votes, yes, no = (int(n) for n, _ in numbers[:4])
    extras = numbers[4:]
    challenged_pop = challenged_votes = ""
    if len(extras) == 2:
        challenged_pop, challenged_votes = extras[0][0], extras[1][0]
    elif len(extras) == 1:
        value, x = extras[0]
        if len(challenged_x or []) >= 2:
            # Nearer the second "Challenged" header column: challenged votes.
            midpoint = (challenged_x[0] + challenged_x[-1]) / 2
            if x > midpoint:
                challenged_votes = value
            else:
                challenged_pop = value
        else:
            challenged_pop = value
    meets = ""
    if pop > 0:
        meets = "true" if yes * 100 >= 51 * pop else "false"
    return {
        "unit_code": start.group("code"),
        "employer_name": re.sub(r"\s+", " ", employer),
        "union_name": re.sub(r"\s+", " ", union),
        "bargaining_unit_name": re.sub(r"\s+", " ", unit),
        "unit_population": str(pop),
        "votes_cast": str(votes),
        "votes_yes": str(yes),
        "votes_no": str(no),
        "challenged_unit_population": challenged_pop,
        "challenged_votes": challenged_votes,
        "meets_51pct_threshold": meets,
    }


def _parse_result_text(
    text: str,
    *,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    cycle = _election_cycle_from_url(pdf_url)
    as_of = _HEADING_AS_OF_RE.search(text)
    window = _HEADING_WINDOW_RE.search(text)
    challenged_x = _challenged_columns(text)
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        parsed = parse_tally_line(line, challenged_x=challenged_x)
        if not parsed:
            continue
        row_key = f"{AGENCY_CODE}:{cycle}:{parsed['unit_code']}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "unit_code": parsed["unit_code"],
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "ANNUAL_CERTIFICATION_ELECTION",
                "employer_name": parsed["employer_name"],
                "union_name": parsed["union_name"],
                "bargaining_unit_name": parsed["bargaining_unit_name"],
                "unit_population": parsed["unit_population"],
                "votes_cast": parsed["votes_cast"],
                "votes_yes": parsed["votes_yes"],
                "votes_no": parsed["votes_no"],
                "challenged_unit_population": parsed["challenged_unit_population"],
                "challenged_votes": parsed["challenged_votes"],
                "meets_51pct_threshold": parsed["meets_51pct_threshold"],
                "document_status": ENDPOINT_TALLY,
                "tally_as_of": re.sub(r"\s+", " ", as_of.group("as_of")).strip() if as_of else "",
                "election_open_date": _iso_mdy(window.group("open")) if window else "",
                "election_close_date": _iso_mdy(window.group("close")) if window else "",
                "jurisdiction_city": _jurisdiction_city(parsed["employer_name"]),
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

