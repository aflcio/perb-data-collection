"""New Mexico PELRB public bargaining-unit roster.

WHAT THIS FILE IS FOR
---------------------
Download the "All Known State and Local Public Bargaining Units" PDF linked from
pelrb.nm.gov, parse one row per employer×unit, then hand rows to the shared
state-PERB ACE (GeoCensus) path.

Grain: one bargaining unit under an employer (or state agency under a union in
the state-employee section). Source PDF is periodically re-uploaded; the scrape
discovers the current href from the landing page.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, fetch_bytes
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NM PELRB Bargaining Units Flow"
REPORT_PREFIX = "nm_pelrb_bargaining_units"
AGENCY_CODE = "NM_PELRB"
BASE_URL = "https://www.pelrb.nm.gov"
LISTING_URL = f"{BASE_URL}/nm-public-bargaining/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "canonical_case_type",
    "native_case_type",
    "jurisdiction_section",
    "employer_name",
    "union_name",
    "bargaining_unit_name",
    "unit_letter",
    "approx_employees",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "roster_as_of_date",
    "source_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_PDF_HREF_RE = re.compile(
    r'href="([^"]*All-Known-State-and-Local-Public-Bargaining-Units[^"]+\.pdf)"',
    flags=re.I,
)
_SECTION_RE = re.compile(
    r"^\s*(UNITS SUBJECT TO LOCAL BOARDS|"
    r"UNIONS REPRESENTING STATE EMPLOYEES|"
    r"LOCAL BARGAINING UNITS SUBJECT TO THE PELRB)\s*:?\s*$",
    flags=re.I,
)
_EMP_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_UNIT_RE = re.compile(r"^\s*([a-z])\.\s+(.+?)\s*$", flags=re.I)
_ROMAN_OUTLINE_RE = re.compile(
    r"^\s*(i{1,3}|iv|vi{0,3}|ix|x)\.\s+",
    flags=re.I,
)
# Tolerate doubled periods in the roster ("approx.. 10 employees").
_APPROX_RE = re.compile(
    r"\(approx\.+\s*([\d,]+)\s+employees?\)\.?",
    flags=re.I,
)
_APPROX_INLINE_RE = re.compile(
    r"approx\.+\s*([\d,]+)\s+employees?",
    flags=re.I,
)
_AS_OF_HEADER_RE = re.compile(
    r"Updated\s+(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<year>(?:19|20)\d{2})",
    flags=re.I,
)
_AS_OF_FILENAME_RE = re.compile(
    r"-(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)-(?P<year>(?:19|20)\d{2})\.pdf$",
    flags=re.I,
)
_MONTH_NUM = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}
_UNIONISH_RE = re.compile(
    r"\b(Association|Ass'?n|Union|Federation|AFSCME|NEA|AFT|CWA|IAFF|Teamsters|"
    r"Council\s+\d+)\b",
    flags=re.I,
)
_PAGE_FOOTER_RE = re.compile(r"^\s*\d+\s*\|\s*P\s*a\s*g\s*e\s*$", flags=re.I)

_SECTION_SLUGS = {
    "UNITS SUBJECT TO LOCAL BOARDS": "local_boards",
    "UNIONS REPRESENTING STATE EMPLOYEES": "state_employees",
    "LOCAL BARGAINING UNITS SUBJECT TO THE PELRB": "pelrb_local",
}

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

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
                "pdftotext is required to parse NM PELRB bargaining-unit PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftotext failed: {exc.stderr or exc.stdout or exc}"
            ) from exc
        return completed.stdout

def discover_units_pdf_url(html: str) -> str:
    match = _PDF_HREF_RE.search(html)
    if not match:
        raise RuntimeError(
            f"No All-Known-State-and-Local-Public-Bargaining-Units PDF on {LISTING_URL}"
        )
    return _absolute_url(match.group(1))

def _clean_text(value: str) -> str:
    text = (
        value.replace("\xa0", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    return re.sub(r"\s+", " ", text).strip()

def _extract_approx(body: str) -> tuple[str, str]:
    match = _APPROX_RE.search(body) or _APPROX_INLINE_RE.search(body)
    if not match:
        return body.strip().rstrip("."), ""
    approx = match.group(1).replace(",", "")
    cleaned = _APPROX_RE.sub("", body)
    cleaned = _APPROX_INLINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".,:")
    return cleaned, approx

def _split_union_and_unit(body: str) -> tuple[str, str]:
    """Prefer last substantive parenthetical as unit description."""
    parens = list(re.finditer(r"\(([^)]+)\)", body))
    if not parens:
        return body, ""
    last = parens[-1]
    inner = last.group(1).strip()
    if re.fullmatch(r"(Local\s+)?\d+", inner, flags=re.I):
        return body, ""
    if len(inner) < 6:
        return body, ""
    union = body[: last.start()].strip().rstrip(",").strip()
    return union or body, inner

def _jurisdiction_city(employer_name: str) -> str:
    """Return a city only when the employer string explicitly encodes one.

    Counties, school districts, authorities, and universities are not cities —
    leave those empty rather than copying the employer into ACE's city field
    (infra-42).
    """
    name = employer_name.strip()
    if "," in name:
        left, right = name.split(",", 1)
        # "Albuquerque, City of" → Albuquerque
        if re.search(r"\b(City|Town|Village)\s+of\b", right, flags=re.I):
            return left.strip()
    return ""


def _roster_as_of_date(*, text: str, pdf_url: str) -> str:
    """ISO month date (YYYY-MM-01) from roster header or PDF filename."""
    match = _AS_OF_HEADER_RE.search(text) or _AS_OF_FILENAME_RE.search(pdf_url)
    if not match:
        return ""
    mon = _MONTH_NUM.get(match.group("mon").lower().rstrip("."), "")
    year = match.group("year")
    return f"{year}-{mon}-01" if mon else ""


def _looks_like_union(name: str) -> bool:
    return bool(_UNIONISH_RE.search(name))


def _unit_without_union(body: str) -> bool:
    """True when the roster entry is a unit description with no bargaining agent."""
    if _looks_like_union(body):
        return False
    # Typical no-union form: "Anthony Police Dept (Full-time …)"
    return bool(re.match(r"^[A-Z].+\([^)]+\)\s*$", body.strip()))

def _slug_employer(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().upper()).strip("_")
    return slug[:80] or "UNKNOWN"

def parse_units_text(
    text: str,
    *,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    """Parse pdftotext layout output into wide staging rows."""
    section = ""
    employer = ""
    parent_union = ""
    state_heading_is_employer = False
    rows: list[dict[str, str]] = []
    buf: list[str] = []
    mode: str | None = None
    roster_as_of = _roster_as_of_date(text=text, pdf_url=pdf_url)

    def flush() -> None:
        nonlocal buf, mode, employer, parent_union, state_heading_is_employer
        if not buf or not mode:
            buf = []
            return
        joined = _clean_text(" ".join(buf))
        buf = []
        if mode == "emp":
            match = _EMP_RE.match(joined) or re.match(r"^(\d+)\.\s+(.+)$", joined)
            if not match:
                return
            name = match.group(2).strip().rstrip(":")
            name, _ = _extract_approx(name)
            if section == "UNIONS REPRESENTING STATE EMPLOYEES":
                # Most headings are unions (AFSCME Council 18). The School for the
                # Deaf block titles the employer and puts the association under
                # the unit letter (infra-42).
                if _looks_like_union(name):
                    parent_union = name
                    employer = "State of New Mexico"
                    state_heading_is_employer = False
                else:
                    parent_union = ""
                    employer = name
                    state_heading_is_employer = True
            else:
                employer = name
                parent_union = ""
                state_heading_is_employer = False
            return

        match = re.match(r"^([a-z])\.\s+(.+)$", joined, flags=re.I)
        if not match or not employer:
            return
        letter = match.group(1).lower()
        body, approx = _extract_approx(match.group(2).strip())
        section_slug = _SECTION_SLUGS.get(section, section.lower().replace(" ", "_"))

        if section == "UNIONS REPRESENTING STATE EMPLOYEES":
            if state_heading_is_employer:
                employer_name = employer
                if _looks_like_union(body.split("(")[0]):
                    union_name, unit_name = _split_union_and_unit(body)
                else:
                    union_name, unit_name = "", body
            else:
                agency = body.split("(")[0].strip() or body
                union_name = parent_union or body
                unit_name = body
                employer_name = agency
        elif _unit_without_union(body):
            # Roster lists a unit with no bargaining agent — do not invent a union.
            employer_name = employer
            union_name = ""
            unit_name = body
        else:
            union_name, unit_name = _split_union_and_unit(body)
            employer_name = employer
            if not unit_name and union_name == body:
                # Entire body is the union with no separate unit parenthetical.
                unit_name = ""

        row_key = (
            f"{AGENCY_CODE}:{section_slug}:"
            f"{_slug_employer(employer_name)}:{letter}"
        )
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "BARGAINING_UNIT_ROSTER",
                "jurisdiction_section": section_slug,
                "employer_name": employer_name,
                "union_name": union_name,
                "bargaining_unit_name": unit_name,
                "unit_letter": letter,
                "approx_employees": approx,
                "jurisdiction_city": _jurisdiction_city(employer_name),
                "jurisdiction_state": "NM",
                "employer_street": "",
                "employer_zip": "",
                "roster_as_of_date": roster_as_of,
                "source_pdf_url": pdf_url,
                "source_page_url": LISTING_URL,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _PAGE_FOOTER_RE.match(line):
            continue
        if re.search(r"NEW MEXICO PUBLIC BARGAINING|UNIT INFORMATION", line, re.I):
            continue
        # Keep "Updated Feb. 2026" lines for as-of extraction; do not treat as content.
        if _AS_OF_HEADER_RE.search(line):
            continue
        if re.search(r"^Table of Contents", line, re.I):
            continue

        section_match = _SECTION_RE.match(line.strip())
        if section_match:
            flush()
            section = section_match.group(1).upper()
            mode = None
            continue

        # Nested Roman outlines under state departments — keep as continuation
        # of the current unit, not as a new unit letter.
        if section == "UNIONS REPRESENTING STATE EMPLOYEES" and _ROMAN_OUTLINE_RE.match(
            line
        ):
            if mode == "unit" and buf:
                buf.append(line)
            continue

        if _EMP_RE.match(line):
            flush()
            mode = "emp"
            buf = [line]
            continue

        if _UNIT_RE.match(line) and not _ROMAN_OUTLINE_RE.match(line):
            flush()
            mode = "unit"
            buf = [line]
            continue

        if mode and buf:
            buf.append(line)

    flush()
    return rows

def scrape_bargaining_units(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    fetch_pdf: Any = None,
    parse_text: Any = None,
) -> list[dict[str, str]]:
    html_fetcher = fetch_html or fetch_url
    pdf_fetcher = fetch_pdf or fetch_bytes
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = html_fetcher(LISTING_URL, delay_seconds=delay_seconds)
    pdf_url = discover_units_pdf_url(html)
    pdf_bytes = pdf_fetcher(pdf_url, delay_seconds=delay_seconds)
    text = parse_text(pdf_bytes) if parse_text else _pdf_to_text(pdf_bytes)
    rows = parse_units_text(text, pdf_url=pdf_url, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"NM PELRB bargaining-units PDF parsed 0 rows: {pdf_url}")
    rows.sort(key=lambda row: row["row_key"])
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_bargaining_units(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

