"""Kansas PEERA per-employer unit rosters.

WHAT THIS FILE IS FOR
---------------------
Scrape the PEERA covered-employer / unit roster published by KS DOL.

Primary source is labordecisions.dol.ks.gov (reachable when www is blocked);
www.dol.ks.gov is often Akamai-gated from datacenter IPs, so HTTP 403 falls
back to Playwright (optional ``[browser]`` extra), then to the labordecisions
mirror.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from perb_data_collection.http import fetch_url, strip_html_text, DEFAULT_USER_AGENT
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "KS PEERA Unit Rosters Flow"
REPORT_PREFIX = "ks_peera_unit_rosters"
AGENCY_CODE = "KS_PEERA"

# Primary: ASP.NET decisions host (works when www.dol.ks.gov is Akamai-blocked).
ROSTER_PRIMARY_URL = "https://labordecisions.dol.ks.gov/PEERADocumentSearch"
# Secondary: cms page (may 403 from datacenter IPs; Playwright retry helps some hosts).
ROSTER_FALLBACK_URL = (
    "https://www.dol.ks.gov/labor-relations/"
    "public-employer-employee-relations-act-peera-decisions.html"
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "employer_name",
    "bargaining_unit_name",
    "representation_status",
    "canonical_case_type",
    "native_case_type",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_CITIES_RE = re.compile(
    r"<strong>\s*Cities\s*</strong>\s*:\s*(.*?)<br\s*/?>",
    flags=re.I | re.S,
)
_COUNTIES_RE = re.compile(
    r"<strong>\s*Counties\s*</strong>\s*:\s*(.*?)<br\s*/?>",
    flags=re.I | re.S,
)
# City-style list splitter that keeps commas inside parentheses.
_COMMA_SPLIT_RE = re.compile(r",\s*(?![^()]*\))")
_COUNTY_KEEP_RE = re.compile(
    r"\b(USD|County|Fire|Unified|District|Government)\b",
    flags=re.I,
)

def _slugify_employer(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().upper()).strip("_")
    return slug[:80] or "UNKNOWN"

def _status_from_star(text: str) -> tuple[str, str, str]:
    """Return (clean_text, representation_status, canonical_case_type)."""
    marked = text.rstrip().endswith("*") or "decertified" in text.lower()
    clean = text.rstrip().rstrip("*").strip()
    if marked:
        return clean, "DECERTIFIED", "DECERTIFICATION"
    return clean, "CERTIFIED", "CERTIFICATION"

def _jurisdiction_city(employer_name: str) -> str:
    paren = re.search(r"\(([^)]+)\)", employer_name)
    if paren:
        city = paren.group(1).strip()
        city = re.sub(r",?\s*KS\.?$", "", city, flags=re.I).strip()
        return city
    # Drop trailing ", KS" and " County" for ACE city hint.
    city = re.sub(r",?\s*KS\.?$", "", employer_name, flags=re.I).strip()
    city = re.sub(r"\s+County$", "", city, flags=re.I).strip()
    return city.split("/")[0].strip()

def _row(
    *,
    employer_name: str,
    unit_name: str,
    status: str,
    canonical: str,
    page_url: str,
    scraped_at: str,
) -> dict[str, str]:
    employer_slug = _slugify_employer(employer_name)
    unit_slug = _slugify_employer(unit_name) if unit_name else "EMPLOYER"
    return {
        "row_key": f"{AGENCY_CODE}:{employer_slug}:{unit_slug}",
        "source_agency_code": AGENCY_CODE,
        "employer_name": employer_name,
        "bargaining_unit_name": unit_name,
        "representation_status": status,
        "canonical_case_type": canonical,
        "native_case_type": "PEERA_UNIT_ROSTER",
        "jurisdiction_city": _jurisdiction_city(employer_name),
        "jurisdiction_state": "KS",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": page_url,
        "source_url": page_url,
        "scraped_at": scraped_at,
    }

def _split_prose_entries(body: str) -> list[str]:
    """Split comma lists; reattach trailing `, KS.` fragments incorrectly split."""
    parts = [part.strip() for part in _COMMA_SPLIT_RE.split(body) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and re.fullmatch(r"KS\.?", part, flags=re.I):
            merged[-1] = f"{merged[-1]}, {part}"
        else:
            merged.append(part)
    return merged

def _normalize_county_employer(name: str) -> str:
    """Disambiguate bare county names from same-named cities (e.g. Ellis County)."""
    if _COUNTY_KEEP_RE.search(name):
        return name
    return f"{name} County"

def _parse_employer_entry(
    entry: str,
    *,
    page_url: str,
    scraped_at: str,
    section: str,
) -> list[dict[str, str]]:
    """Parse one Cities/Counties list entry into unit rows."""
    entry = strip_html_text(entry).strip().strip(",")
    if not entry:
        return []

    # "USD 500 (Kansas City, KS) - Clerical; Paraprofessional; Shop & Maintenance*"
    if " - " in entry:
        employer_raw, units_raw = entry.split(" - ", 1)
        employer_clean, employer_status, employer_canonical = _status_from_star(employer_raw)
        employer_name = (
            _normalize_county_employer(employer_clean)
            if section == "COUNTIES"
            else employer_clean
        )
        units = [u.strip() for u in units_raw.split(";") if u.strip()]
        if units:
            rows = []
            for unit_raw in units:
                unit_name, status, canonical = _status_from_star(unit_raw)
                rows.append(
                    _row(
                        employer_name=employer_name,
                        unit_name=unit_name,
                        status=status,
                        canonical=canonical,
                        page_url=page_url,
                        scraped_at=scraped_at,
                    )
                )
            return rows
        return [
            _row(
                employer_name=employer_name,
                unit_name="",
                status=employer_status,
                canonical=employer_canonical,
                page_url=page_url,
                scraped_at=scraped_at,
            )
        ]

    employer_clean, status, canonical = _status_from_star(entry)
    employer_name = (
        _normalize_county_employer(employer_clean)
        if section == "COUNTIES"
        else employer_clean
    )
    return [
        _row(
            employer_name=employer_name,
            unit_name="",
            status=status,
            canonical=canonical,
            page_url=page_url,
            scraped_at=scraped_at,
        )
    ]

def _parse_cities_counties_prose(html: str, *, page_url: str, scraped_at: str) -> list[dict[str, str]]:
    """Parse labordecisions <strong>Cities</strong>: … / <strong>Counties</strong>: … prose."""
    rows: list[dict[str, str]] = []
    for section, pattern in (("CITIES", _CITIES_RE), ("COUNTIES", _COUNTIES_RE)):
        match = pattern.search(html)
        if not match:
            continue
        body = strip_html_text(match.group(1))
        for entry in _split_prose_entries(body):
            rows.extend(
                _parse_employer_entry(
                    entry,
                    page_url=page_url,
                    scraped_at=scraped_at,
                    section=section,
                )
            )
    return rows

def _parse_unit_lines(block: str) -> list[tuple[str, str, str]]:
    units: list[tuple[str, str, str]] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("bargaining unit"):
            continue
        unit_name, status, canonical = _status_from_star(line)
        if not unit_name:
            continue
        units.append((unit_name, status, canonical))
    return units

def _parse_legacy_strong_blocks(html: str, *, page_url: str, scraped_at: str) -> list[dict[str, str]]:
    """Legacy CMS layout: one <strong>employer</strong> followed by unit lines."""
    rows: list[dict[str, str]] = []
    employer_blocks = re.split(
        r"(?=<(?:strong|b)[^>]*>\s*[^<]+\s*</(?:strong|b)>)",
        html,
        flags=re.I,
    )
    for block in employer_blocks:
        header = re.search(
            r"<(?:strong|b)[^>]*>\s*([^<]+?)\s*</(?:strong|b)>",
            block,
            flags=re.I,
        )
        if not header:
            continue
        employer_name = strip_html_text(header.group(1))
        if not employer_name or employer_name.lower() in {
            "peera",
            "decisions",
            "cities",
            "counties",
        }:
            continue
        after_header = block.split(header.group(0), 1)[-1]
        units = _parse_unit_lines(strip_html_text(after_header))
        if not units:
            continue
        for unit_name, status, canonical in units:
            rows.append(
                _row(
                    employer_name=employer_name,
                    unit_name=unit_name,
                    status=status,
                    canonical=canonical,
                    page_url=page_url,
                    scraped_at=scraped_at,
                )
            )
    return rows

def _parse_roster_html(html: str, *, page_url: str, scraped_at: str) -> list[dict[str, str]]:
    rows = _parse_cities_counties_prose(html, page_url=page_url, scraped_at=scraped_at)
    if rows:
        return rows
    return _parse_legacy_strong_blocks(html, page_url=page_url, scraped_at=scraped_at)

def fetch_html_playwright(url: str, *, timeout_ms: int = 120_000) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()

def fetch_ks_html(url: str, *, delay_seconds: float = 0.3) -> str:
    try:
        return fetch_url(url, delay_seconds=delay_seconds)
    except RuntimeError as exc:
        if "403" not in str(exc):
            raise
    return fetch_html_playwright(url)

def _html_looks_blocked(html: str) -> bool:
    return "access denied" in html.lower() and "akamai" in html.lower() or (
        "access denied" in html.lower() and len(html) < 2_000
    )

def scrape_unit_rosters(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_ks_html
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    pages = [ROSTER_PRIMARY_URL, ROSTER_FALLBACK_URL]
    last_error: Exception | None = None
    for page_url in pages:
        try:
            html = fetcher(page_url, delay_seconds=delay_seconds)
        except Exception as exc:  # noqa: BLE001 — try next source
            last_error = exc
            continue
        if _html_looks_blocked(html):
            last_error = RuntimeError(f"KS PEERA page blocked: {page_url}")
            continue
        rows = _parse_roster_html(html, page_url=page_url, scraped_at=scraped_at)
        if rows:
            rows.sort(key=lambda row: (row["employer_name"], row["bargaining_unit_name"]))
            return rows
        last_error = RuntimeError(f"KS PEERA page parsed 0 unit rows: {page_url}")
    if last_error:
        raise RuntimeError(f"KS PEERA scrape failed after trying {pages}") from last_error
    raise RuntimeError(f"KS PEERA scrape failed after trying {pages}")

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_unit_rosters(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

