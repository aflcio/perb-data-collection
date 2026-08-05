"""Maine MLRB unit/representation case index.

WHAT THIS FILE IS FOR
---------------------
Enumerate the legacy Unit/Representation decision index at
maine.gov/mlrb/decisions/rep/, fetch each case HTML title for party labels,
map case-number prefixes into the shared canonical_case_type enum, then run
shared state-PERB ACE (GeoCensus).

Maine is one of the few boards that also tracks voluntary recognition /
unit-agreement notices in process docs; those case files live in this same
representation index (prefixes E/UC/UD/…). PPC (unfair practice) stays out of
scope for this feed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "ME MLRB Unit Representation Cases Flow"
REPORT_PREFIX = "me_mlrb_unit_rep_cases"
AGENCY_CODE = "ME_MLRB"
BASE_URL = "https://www.maine.gov"
INDEX_URL = f"{BASE_URL}/mlrb/decisions/rep/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "document_title",
    "decision_date",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

# Filename stem → native prefix / canonical default.
_CASE_FILE_RE = re.compile(
    r"^(?P<stem>(?P<yy>\d{2})-(?P<prefix>[A-Z]+)(?:-(?P<seq>\d+[A-Z]?))?)\.htm$",
    flags=re.I,
)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", flags=re.I | re.S)
_DATE_IN_TITLE_RE = re.compile(
    r",\s*(?P<date>(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4})\s*$",
    flags=re.I,
)

_PREFIX_CANONICAL = {
    "E": "CERTIFICATION",
    "EA": "CERTIFICATION",
    "UC": "UNIT_CLARIFICATION",
    "UCA": "UNIT_CLARIFICATION",
    "UD": "UNIT_MODIFICATION",
    "UDA": "UNIT_MODIFICATION",
    "A": "ARBITRATION",
    "MERGER": "UNIT_MODIFICATION",
    "IR": "CERTIFICATION",
    "AP": "CERTIFICATION",
}
# Atlantic Reporter cites dumped into this directory (e.g. 354A2d154.htm).
_REPORTER_CITE_RE = re.compile(r"^\d+A2d\d+\.htm$", flags=re.I)

def _absolute_url(href: str) -> str:
    return urljoin(INDEX_URL, href)

def _normalize_case_number(stem: str) -> str:
    return stem.strip().upper()

def list_case_files(html: str) -> list[str]:
    """Return unique .htm case filenames from the Apache-style directory listing."""
    found: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="([^"]+\.htm)"', html, flags=re.I):
        name = href.rsplit("/", 1)[-1]
        if not re.match(r"^[\w.-]+\.htm$", name, flags=re.I):
            continue
        if _REPORTER_CITE_RE.match(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    found.sort(key=str.lower)
    return found

def _prefix_from_filename(filename: str) -> str:
    match = _CASE_FILE_RE.match(filename)
    if match:
        return match.group("prefix").upper()
    # e.g. CV-84-235.htm
    parts = filename.rsplit(".", 1)[0].upper().split("-")
    if parts and parts[0].isalpha():
        return parts[0]
    if len(parts) >= 2 and parts[1].isalpha():
        return parts[1]
    return "UNKNOWN"

def _canonical_from_title(prefix: str, title: str) -> tuple[str, str]:
    native = prefix
    lowered = title.lower()
    if "decertif" in lowered:
        return "DECERTIFICATION", native
    if "voluntary recognition" in lowered or "unit agreement" in lowered:
        return "RECOGNITION", native
    if "unit clarification" in lowered:
        return "UNIT_CLARIFICATION", native
    canonical = _PREFIX_CANONICAL.get(prefix.upper(), "CERTIFICATION")
    return canonical, native

def _parties_from_title(title: str) -> tuple[str, str, str]:
    """Return (employer_name, union_name, decision_date) heuristics from <title>."""
    cleaned = strip_html_text(title)
    decision_date = ""
    date_match = _DATE_IN_TITLE_RE.search(cleaned)
    if date_match:
        decision_date = date_match.group("date")
        cleaned = cleaned[: date_match.start()].rstrip().rstrip(",")

    # Drop trailing ", No. YY-XX-NN"
    cleaned = re.sub(r",\s*No\.\s*[\w-]+\s*$", "", cleaned, flags=re.I).strip()

    # "In Re: Petition for Decertification, EMPLOYER ..."
    in_re = re.match(r"^In\s+Re:\s*(.+)$", cleaned, flags=re.I)
    if in_re:
        body = in_re.group(1).strip()
        body = re.sub(
            r"^Petition for (?:Decertification|Certification)\s*,?\s*",
            "",
            body,
            flags=re.I,
        ).strip()
        # Often "SAD 5 Bus Drivers (MEA and Teamsters)"
        paren = re.search(r"\(([^)]+)\)\s*$", body)
        if paren:
            return body[: paren.start()].strip(), paren.group(1).strip(), decision_date
        return body, "", decision_date

    # "Union and Employer" / "Employer and Union"
    if " and " in cleaned:
        left, right = cleaned.split(" and ", 1)
        left, right = left.strip(), right.strip()
        # Prefer public-employer-looking side as employer.
        employer_hints = (
            "msad",
            "sad",
            "rsu",
            "school",
            "city",
            "town",
            "county",
            "university",
            "college",
            "state",
            "district",
        )
        left_is_emp = any(h in left.lower() for h in employer_hints)
        right_is_emp = any(h in right.lower() for h in employer_hints)
        if right_is_emp and not left_is_emp:
            return right, left, decision_date
        if left_is_emp and not right_is_emp:
            return left, right, decision_date
        return right, left, decision_date

    return cleaned, "", decision_date

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    if not name:
        return ""
    name = re.sub(r"^(City|Town|Village)\s+of\s+", "", name, flags=re.I)
    return name.split(",")[0].strip()

def parse_case_title(
    *,
    filename: str,
    title: str,
    case_url: str,
    scraped_at: str,
) -> dict[str, str]:
    stem = filename.rsplit(".", 1)[0]
    case_number = _normalize_case_number(stem)
    prefix = _prefix_from_filename(filename)
    canonical, native = _canonical_from_title(prefix, title)
    employer_name, union_name, decision_date = _parties_from_title(title)
    return {
        "row_key": f"{AGENCY_CODE}:{case_number}",
        "source_agency_code": AGENCY_CODE,
        "case_number": case_number,
        "canonical_case_type": canonical,
        "native_case_type": native,
        "employer_name": employer_name,
        "union_name": union_name,
        "document_title": strip_html_text(title),
        "decision_date": decision_date,
        "jurisdiction_city": _jurisdiction_city(employer_name),
        "jurisdiction_state": "ME",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": INDEX_URL,
        "source_url": case_url,
        "scraped_at": scraped_at,
    }

def scrape_unit_rep_cases(
    *,
    delay_seconds: float = 0.2,
    fetch_html: Any = None,
    fetch_case_titles: bool = True,
) -> list[dict[str, str]]:
    """Scrape the representation index; optionally hydrate titles per case file."""
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    index_html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    files = list_case_files(index_html)
    if not files:
        raise RuntimeError(f"ME MLRB unit/rep index parsed 0 case files: {INDEX_URL}")

    rows: list[dict[str, str]] = []
    for filename in files:
        case_url = _absolute_url(filename)
        title = filename
        if fetch_case_titles:
            page = fetcher(case_url, delay_seconds=delay_seconds)
            match = _TITLE_RE.search(page)
            if match:
                title = strip_html_text(match.group(1))
        rows.append(
            parse_case_title(
                filename=filename,
                title=title,
                case_url=case_url,
                scraped_at=scraped_at,
            )
        )

    rows.sort(key=lambda row: row["case_number"])
    return rows

def scrape_to_wide_csv(
    csv_path: Any,
    *,
    delay_seconds: float = 0.2,
    fetch_case_titles: bool = True,
) -> int:
    rows = scrape_unit_rep_cases(
        delay_seconds=delay_seconds,
        fetch_case_titles=fetch_case_titles,
    )
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

