"""Florida PERC certification registry → employer ACE (GeoCensus) → Redshift.

WHAT THIS FILE IS FOR
---------------------
Harvest the public "Search for PERC Certifications" results grid at
perc.myflorida.com. Empty attribute searches are rejected, so we pull high-yield
substring queries (Union=a, Employer=a/e), merge on certification number, fill
gaps with CertNo= GETs, then probe a short range past the observed max for new
IDs. Listing rows already carry employer/union for ACE; PDF unit text is optional
follow-on work.

Note: this engineering host often cannot curl perc.myflorida.com; Prefect workers
are assumed able to reach it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urlencode, urljoin, unquote

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "FL PERC Certifications Flow"
REPORT_PREFIX = "fl_perc_certifications"
AGENCY_CODE = "FL_PERC"
BASE_URL = "https://perc.myflorida.com"
SEARCH_URL = f"{BASE_URL}/co/certfilter.aspx"
RESULTS_PATH = "/co/certResults.aspx"

# High-yield substring queries (empty Union+Employer is rejected by PERC).
BULK_QUERIES: tuple[tuple[str, str], ...] = (
    ("Union", "a"),
    ("Employer", "a"),
    ("Employer", "e"),
)

# How far past observed max(cert) to probe with CertNo= GETs.
GAP_PROBE_AHEAD = 50

# Sanity floor: Union=a alone returned ~2,175 rows in the 2026-07-19 research pass.
MIN_EXPECTED_ROWS = 1500

PLACEHOLDER_UNIONS = frozenset({"-0-", "0", "-", "n/a", "na", "none"})

# Stable per-cert permalink (bulk Union=/Employer= result pages are not durable).
CERT_RESULTS_URL = f"{BASE_URL}{RESULTS_PATH}"

def cert_permalink(cert_no: str | int) -> str:
    """Return the durable CertNo= results URL for a certification number."""
    return f"{CERT_RESULTS_URL}?{urlencode({'CertNo': str(cert_no)})}"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "certification_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "certification_pdf_url",
    "pdf_file_name",
    "source_page_url",
    "source_url",
    "scraped_at",
)

def _results_url(*, cert_no: int | None = None, union: str = "", employer: str = "") -> str:
    if cert_no is not None:
        return f"{BASE_URL}{RESULTS_PATH}?{urlencode({'CertNo': str(cert_no)})}"
    return f"{BASE_URL}{RESULTS_PATH}?{urlencode({'Union': union, 'Employer': employer})}"

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href.lstrip("/"))

def _is_placeholder_union(union_name: str) -> bool:
    return union_name.strip().lower() in PLACEHOLDER_UNIONS

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    if not name:
        return ""
    name = re.sub(r",\s*Florida\s*$", "", name, flags=re.I).strip()
    return name.split(",")[0].strip()[:80]

def parse_certification_table(html: str, *, scraped_at: str, source_page_url: str = "") -> list[dict[str, str]]:
    """Parse the ASP.NET `#gridCases` results table into wide-row dicts.

    ``source_page_url`` is the scrape origin (bulk or CertNo query). It is not
    stored — each row uses ``cert_permalink(cert_no)`` as the durable link.
    """
    _ = source_page_url
    table_match = re.search(
        r'<table[^>]*id=["\']gridCases["\'][^>]*>(.*?)</table>',
        html,
        flags=re.I | re.S,
    )
    if not table_match:
        return []

    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
        if re.search(r"<th\b", row_html, flags=re.I):
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 3:
            continue

        cert_raw = strip_html_text(cells[0])
        if not re.fullmatch(r"\d+", cert_raw):
            continue
        cert_no = cert_raw
        union_name = strip_html_text(cells[1])
        employer_name = strip_html_text(cells[2]) if len(cells) > 2 else ""

        href_match = re.search(r'href="([^"]+)"', cells[3] if len(cells) > 3 else row_html, flags=re.I)
        pdf_url = ""
        pdf_file = ""
        if href_match:
            href = unescape(href_match.group(1).strip())
            pdf_url = _absolute_url(href)
            file_match = re.search(r"[?&]File=([^&]+)", href, flags=re.I)
            if not file_match:
                file_match = re.search(r"[?&]File=([^&]+)", pdf_url, flags=re.I)
            if file_match:
                pdf_file = unquote(file_match.group(1))

        has_employer = bool(employer_name.strip()) and not _is_placeholder_union(union_name)
        permalink = cert_permalink(cert_no)
        rows.append(
            {
                "row_key": f"{AGENCY_CODE}:{cert_no}",
                "source_agency_code": AGENCY_CODE,
                "certification_number": cert_no,
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": "CERTIFICATION",
                "employer_name": employer_name,
                "union_name": "" if _is_placeholder_union(union_name) else union_name,
                "jurisdiction_city": _jurisdiction_city(employer_name) if has_employer else "",
                "jurisdiction_state": "FL" if has_employer else "",
                "employer_street": "",
                "employer_zip": "",
                "certification_pdf_url": pdf_url,
                "pdf_file_name": pdf_file,
                # Always the CertNo= page — never the bulk Union=/Employer= result URL.
                "source_page_url": permalink,
                "source_url": pdf_url or permalink,
                "scraped_at": scraped_at,
            }
        )
    return rows

def _merge_rows(into: dict[str, dict[str, str]], rows: list[dict[str, str]]) -> None:
    for row in rows:
        key = row["certification_number"]
        existing = into.get(key)
        if existing is None:
            into[key] = row
            continue
        # Prefer the row with a non-blank employer, then non-blank PDF.
        if not existing["employer_name"] and row["employer_name"]:
            into[key] = row
        elif not existing["certification_pdf_url"] and row["certification_pdf_url"]:
            into[key] = row

def scrape_certifications(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    bulk_queries: tuple[tuple[str, str], ...] = BULK_QUERIES,
    gap_probe_ahead: int = GAP_PROBE_AHEAD,
    min_expected_rows: int = MIN_EXPECTED_ROWS,
) -> list[dict[str, str]]:
    """Scrape FL PERC certifications via bulk substring GETs + CertNo gap fill."""
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    by_cert: dict[str, dict[str, str]] = {}

    for field, value in bulk_queries:
        if field == "Union":
            url = _results_url(union=value, employer="")
        elif field == "Employer":
            url = _results_url(union="", employer=value)
        else:
            raise ValueError(f"Unknown bulk query field: {field}")
        html = fetcher(url, delay_seconds=delay_seconds)
        _merge_rows(by_cert, parse_certification_table(html, scraped_at=scraped_at, source_page_url=url))

    if len(by_cert) < min_expected_rows:
        raise RuntimeError(
            f"FL PERC bulk queries returned only {len(by_cert)} certifications "
            f"(expected >= {min_expected_rows}); check host reachability for {SEARCH_URL}"
        )

    cert_ints = sorted(int(c) for c in by_cert)
    max_cert = cert_ints[-1]
    missing = [n for n in range(1, max_cert + 1) if str(n) not in by_cert]

    for cert_no in missing:
        url = _results_url(cert_no=cert_no)
        html = fetcher(url, delay_seconds=delay_seconds)
        _merge_rows(by_cert, parse_certification_table(html, scraped_at=scraped_at, source_page_url=url))

    # Probe past the current max for newly issued certification numbers.
    consecutive_empty = 0
    for cert_no in range(max_cert + 1, max_cert + gap_probe_ahead + 1):
        url = _results_url(cert_no=cert_no)
        html = fetcher(url, delay_seconds=delay_seconds)
        new_rows = parse_certification_table(html, scraped_at=scraped_at, source_page_url=url)
        if not new_rows:
            consecutive_empty += 1
            if consecutive_empty >= 10:
                break
            continue
        consecutive_empty = 0
        _merge_rows(by_cert, new_rows)

    rows = list(by_cert.values())
    rows.sort(key=lambda row: int(row["certification_number"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

