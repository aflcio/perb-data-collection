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
_ISSUED_RE = re.compile(
    r"Issued:\s*(?P<date>(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4})",
    flags=re.I,
)
_PUBLIC_EMPLOYER_RE = re.compile(
    r"(?P<name>[A-Z0-9][^,\n]{2,120}?),\s*(?:\n\s*)?"
    r"(?:Petitioner\s+and\s+)?Public\s+Employer\.?",
    flags=re.I | re.S,
)
_PETITIONER_RE = re.compile(
    r"(?P<name>[A-Z0-9][^,\n]{2,120}?),\s*(?:\n\s*)?Petitioner(?:\s+and\s+Public\s+Employer)?\.?",
    flags=re.I | re.S,
)
_TRAILING_CASE_RE = re.compile(
    r",?\s*(?:No\.\s*)?(?:\d{2}-[A-Z]+(?:-\d+[A-Z]?)?|\d+\s*A\.?\s*2d\s*\d+)\.?\s*$",
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

def _clean_party_name(name: str) -> str:
    cleaned = strip_html_text(name)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(",.")
    cleaned = _TRAILING_CASE_RE.sub("", cleaned).strip().rstrip(",")
    return cleaned


def _parties_from_body(html: str) -> tuple[str, str, str]:
    """Prefer labeled Petitioner / Public Employer blocks over caption order."""
    text = strip_html_text(html)
    text = text.replace("\xa0", " ")
    decision_date = ""
    issued = _ISSUED_RE.search(text)
    if issued:
        decision_date = issued.group("date")

    employer = ""
    union = ""
    emp_match = _PUBLIC_EMPLOYER_RE.search(text)
    if emp_match:
        employer = _clean_party_name(emp_match.group("name"))
        # "Petitioner and Public Employer" means the same party is both.
        if re.search(r"Petitioner\s+and\s+Public\s+Employer", emp_match.group(0), re.I):
            # Find the other party after "and" in the caption block.
            after = text[emp_match.end() : emp_match.end() + 400]
            other = re.search(
                r"\band\b\s*(?P<name>[A-Z0-9][^,\n]{2,120}?)(?:,|\n|$)",
                after,
                flags=re.I,
            )
            if other:
                union = _clean_party_name(other.group("name"))
            return employer, union, decision_date

    pet_match = _PETITIONER_RE.search(text)
    if pet_match:
        petitioner = _clean_party_name(pet_match.group("name"))
        if employer and petitioner and petitioner.lower() != employer.lower():
            union = petitioner
        elif not employer:
            # Petitioner-only without Public Employer label — leave roles unset
            # rather than guessing caption order.
            pass
    if employer:
        return employer, union, decision_date
    return "", "", decision_date


def _parties_from_title(title: str) -> tuple[str, str, str]:
    """Fallback when the decision HTML has no Petitioner / Public Employer labels."""
    cleaned = strip_html_text(title)
    decision_date = ""
    date_match = _DATE_IN_TITLE_RE.search(cleaned)
    if date_match:
        decision_date = date_match.group("date")
        cleaned = cleaned[: date_match.start()].rstrip().rstrip(",")

    cleaned = _TRAILING_CASE_RE.sub("", cleaned).strip().rstrip(",")

    # Split on " v. " as well as " and ".
    splitter = re.split(r"\s+v\.\s+|\s+and\s+", cleaned, maxsplit=1, flags=re.I)
    if len(splitter) == 2:
        left, right = splitter[0].strip(), splitter[1].strip()
        return "", "", decision_date  # do not invent roles from caption order

    in_re = re.match(r"^In\s+Re:\s*(.+)$", cleaned, flags=re.I)
    if in_re:
        body = in_re.group(1).strip()
        body = re.sub(
            r"^Petition for (?:Decertification|Certification)\s*,?\s*",
            "",
            body,
            flags=re.I,
        ).strip()
        paren = re.search(r"\(([^)]+)\)\s*$", body)
        if paren:
            return body[: paren.start()].strip(), paren.group(1).strip(), decision_date
        return body, "", decision_date

    return "", "", decision_date


def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    if not name:
        return ""
    # Do not treat case captions / citations as cities.
    if re.search(r"(?i)\bv\.|No\.|A\.2d", name):
        return ""
    name = re.sub(r"^(City|Town|Village)\s+of\s+", "", name, flags=re.I)
    city = name.split(",")[0].strip()
    if len(city) > 60:
        return ""
    return city


def parse_case_page(
    *,
    filename: str,
    html: str,
    case_url: str,
    scraped_at: str,
) -> dict[str, str]:
    stem = filename.rsplit(".", 1)[0]
    case_number = _normalize_case_number(stem)
    prefix = _prefix_from_filename(filename)
    title_match = _TITLE_RE.search(html)
    title = strip_html_text(title_match.group(1)) if title_match else filename
    canonical, native = _canonical_from_title(prefix, title)

    employer_name, union_name, decision_date = _parties_from_body(html)
    if not employer_name and not union_name:
        employer_name, union_name, title_date = _parties_from_title(title)
        decision_date = decision_date or title_date
    elif not decision_date:
        _, _, title_date = _parties_from_title(title)
        decision_date = title_date

    return {
        "row_key": f"{AGENCY_CODE}:{case_number}",
        "source_agency_code": AGENCY_CODE,
        "case_number": case_number,
        "canonical_case_type": canonical,
        "native_case_type": native,
        "employer_name": employer_name,
        "union_name": union_name,
        "document_title": title,
        "decision_date": decision_date,
        "jurisdiction_city": _jurisdiction_city(employer_name),
        "jurisdiction_state": "ME",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": INDEX_URL,
        "source_url": case_url,
        "scraped_at": scraped_at,
    }


def parse_case_title(
    *,
    filename: str,
    title: str,
    case_url: str,
    scraped_at: str,
) -> dict[str, str]:
    """Back-compat wrapper used by older callers/tests; title-only path."""
    html = f"<html><head><title>{title}</title></head><body></body></html>"
    return parse_case_page(
        filename=filename,
        html=html,
        case_url=case_url,
        scraped_at=scraped_at,
    )

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
        page = ""
        if fetch_case_titles:
            page = fetcher(case_url, delay_seconds=delay_seconds)
        if not page:
            page = f"<html><head><title>{filename}</title></head><body></body></html>"
        rows.append(
            parse_case_page(
                filename=filename,
                html=page,
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

