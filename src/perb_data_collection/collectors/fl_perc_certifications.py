"""Florida PERC certification registry → employer ACE (GeoCensus) → Redshift.

WHAT THIS FILE IS FOR
---------------------
Harvest the public "Search for PERC Certifications" results grid at
perc.myflorida.com. Empty attribute searches are rejected, so we pull high-yield
substring queries (Union=a, Employer=a/e), merge on certification number, fill
gaps with CertNo= GETs, then probe a short range past the observed max for new
IDs. Listing rows already carry employer/union for ACE.

A second pass then reads each row's certification dossier PDF. The grid says
nothing about whether a certification is still in force, and about 37.8% of the
readable dossiers close with an order revoking it, so the grid alone reports
every certification as current. The dossier pass also decides readability from
the PDF bytes rather than from the file name.

Note: this engineering host often cannot curl perc.myflorida.com; Prefect workers
are assumed able to reach it.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from html import unescape
from typing import Any
from urllib.parse import urlencode, urljoin, unquote

from perb_data_collection.http import fetch_bytes, fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.pdf_probe import PdfProbe, extract_text, probe_pdf_bytes

logger = logging.getLogger(__name__)

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
    "is_image_only",
    "text_chars",
    "certification_status",
    "latest_order_title",
    "latest_order_date",
    "revocation_signal",
    "certification_order_date",
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
                "is_image_only": "",
                "text_chars": "",
                "certification_status": "",
                "latest_order_title": "",
                "latest_order_date": "",
                "revocation_signal": "",
                "certification_order_date": "",
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

# --------------------------------------------------------------------------
# Dossier pass: is the PDF readable, and is the certification still in effect?
# --------------------------------------------------------------------------
#
# The linked PDF is not a single order. It is the dossier for one certification
# number: a stack of orders filed over the years, oldest first. So the LAST
# order in the document decides the current status, and the first
# certification-type order gives the date the certification was issued.

STATUS_IN_EFFECT = "in_effect"
STATUS_REVOKED = "revoked"
STATUS_UNKNOWN = "unknown"

# Case-insensitive. Order matters only for which phrase is reported.
REVOCATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("revoking_certification", r"REVOKING\s+CERTIFICATION"),
    ("hereby_revoked", r"is\s+hereby\s+REVOKED"),
    ("certification_revoked", r"certification[^.\n]{0,120}?\bis\s+revoked\b"),
    ("disclaim_granted", r"petition\s+to\s+disclaim\s+interest\s+is\s+GRANTED"),
    ("disclaimer_of_interest", r"disclaimer\s+of\s+interest"),
    ("decertification", r"decertif"),
)

_REVOCATION_RES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.I)) for name, pattern in REVOCATION_PATTERNS
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_MONTH_DATE_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.I,
)
_NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# An order heading is an ALL-CAPS line naming an order or a certification.
_ORDER_TITLE_RE = re.compile(
    r"^[^a-z\n]*\b(?:ORDER|CERTIFICATION)\b[^a-z\n]*$",
    re.M,
)

_CERTIFYING_TITLE_RE = re.compile(r"REVOK|AMEND|DISCLAIM|DECERTIF|DISMISS", re.I)


def _clean_title(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip(" .:_-")[:120]


def _parse_dates(text: str) -> list[date]:
    """Every ``Month D, YYYY`` or ``MM/DD/YYYY`` date in ``text``, in order."""
    found: list[tuple[int, date]] = []
    for match in _MONTH_DATE_RE.finditer(text):
        month = _MONTHS[match.group(1).lower()]
        try:
            found.append((match.start(), date(int(match.group(3)), month, int(match.group(2)))))
        except ValueError:
            continue
    for match in _NUMERIC_DATE_RE.finditer(text):
        try:
            found.append(
                (match.start(), date(int(match.group(3)), int(match.group(1)), int(match.group(2))))
            )
        except ValueError:
            continue
    found.sort(key=lambda pair: pair[0])
    return [value for _, value in found]


def find_order_sections(text: str) -> list[dict[str, Any]]:
    """Split a dossier into its stack of orders, oldest first.

    Each section is ``{"title", "body", "date"}`` where ``date`` is the first
    date printed near the heading (in the heading's own section), or ``None``.
    """
    matches = [
        m for m in _ORDER_TITLE_RE.finditer(text) if len(_clean_title(m.group(0))) >= 5
    ]
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start():end]
        dates = _parse_dates(body)
        sections.append(
            {
                "title": _clean_title(match.group(0)),
                "body": body,
                "date": dates[0] if dates else None,
            }
        )
    return sections


def _revocation_signal(text: str) -> str:
    for _name, pattern in _REVOCATION_RES:
        match = pattern.search(text)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()[:120]
    return ""


def classify_dossier_text(text: str) -> dict[str, str]:
    """Read one dossier's text layer into the five status columns.

    Empty text is ``unknown``: nothing was read, so nothing is claimed.
    """
    blank = {
        "certification_status": STATUS_UNKNOWN,
        "latest_order_title": "",
        "latest_order_date": "",
        "revocation_signal": "",
        "certification_order_date": "",
    }
    if not text or not text.strip():
        return blank

    sections = find_order_sections(text)

    if sections:
        last = sections[-1]
        latest_title = str(last["title"])
        latest_date = last["date"]
        # The last order decides. Fall back to the whole document only when the
        # closing order says nothing either way, so a revocation recorded in an
        # unheaded addendum is not lost.
        signal = _revocation_signal(str(last["body"])) or _revocation_signal(text)
    else:
        latest_title = ""
        latest_date = None
        signal = _revocation_signal(text)

    cert_dates = [
        s["date"]
        for s in sections
        if s["date"] is not None
        and "CERTIFICATION" in str(s["title"]).upper()
        and not _CERTIFYING_TITLE_RE.search(str(s["title"]))
    ]

    return {
        "certification_status": STATUS_REVOKED if signal else STATUS_IN_EFFECT,
        "latest_order_title": latest_title,
        "latest_order_date": latest_date.isoformat() if latest_date else "",
        "revocation_signal": signal,
        "certification_order_date": min(cert_dates).isoformat() if cert_dates else "",
    }


def dossier_columns(pdf_bytes: bytes, *, pdf_to_text: Any = None) -> dict[str, str]:
    """Probe one dossier PDF and classify it into the landed columns."""
    extractor = pdf_to_text or extract_text
    probe: PdfProbe = probe_pdf_bytes(pdf_bytes)

    columns = {
        "is_image_only": "",
        "text_chars": "",
        "certification_status": STATUS_UNKNOWN,
        "latest_order_title": "",
        "latest_order_date": "",
        "revocation_signal": "",
        "certification_order_date": "",
    }

    if probe.is_image_only is None:
        # Unreadable bytes: leave readability empty rather than guess.
        return columns

    columns["is_image_only"] = "true" if probe.is_image_only else "false"
    columns["text_chars"] = str(probe.text_chars)
    if probe.is_image_only:
        return columns

    text = extractor(pdf_bytes) or ""
    if text.strip():
        columns["text_chars"] = str(len(text.strip()))
    columns.update(classify_dossier_text(text))
    return columns


def read_dossiers(
    rows: list[dict[str, str]],
    *,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
    delay_seconds: float = 0.25,
) -> dict[str, int]:
    """Fetch and classify each row's dossier PDF, in place.

    One retry per row on a transient failure; after a second failure the row
    keeps its empty columns, which reads as "not measured" rather than as a
    claim about the certification.
    """
    fetcher = fetch_pdf or fetch_bytes
    stats = {
        "rows": len(rows),
        "pdfs_fetched": 0,
        "image_only": 0,
        "revoked": 0,
        "in_effect": 0,
        "unknown": 0,
        "failures": 0,
    }

    for index, row in enumerate(rows, start=1):
        if index % 200 == 0:
            logger.info(
                "FL PERC dossier pass: %s/%s rows, %s fetched, %s failures",
                index,
                len(rows),
                stats["pdfs_fetched"],
                stats["failures"],
            )

        url = row.get("certification_pdf_url") or ""
        if not url:
            stats["unknown"] += 1
            continue

        data: bytes | None = None
        for attempt in (1, 2):
            try:
                data = fetcher(url, delay_seconds=delay_seconds)
                break
            except Exception as exc:  # noqa: BLE001 - one bad PDF must not end the run
                if attempt == 2:
                    logger.warning(
                        "FL PERC dossier fetch failed twice for cert %s (%s): %s",
                        row.get("certification_number", "?"),
                        url,
                        exc,
                    )
                    data = None

        if data is None:
            stats["failures"] += 1
            stats["unknown"] += 1
            continue

        stats["pdfs_fetched"] += 1
        columns = dossier_columns(data, pdf_to_text=pdf_to_text)
        row.update(columns)

        if columns["is_image_only"] == "true":
            stats["image_only"] += 1
        status = columns["certification_status"]
        if status == STATUS_REVOKED:
            stats["revoked"] += 1
        elif status == STATUS_IN_EFFECT:
            stats["in_effect"] += 1
        else:
            stats["unknown"] += 1

    logger.info(
        "FL PERC dossier pass complete: %s rows, %s PDFs fetched, %s image-only, "
        "%s revoked, %s in effect, %s unknown, %s failures",
        stats["rows"],
        stats["pdfs_fetched"],
        stats["image_only"],
        stats["revoked"],
        stats["in_effect"],
        stats["unknown"],
        stats["failures"],
    )
    return stats


def scrape_certifications(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    bulk_queries: tuple[tuple[str, str], ...] = BULK_QUERIES,
    gap_probe_ahead: int = GAP_PROBE_AHEAD,
    min_expected_rows: int = MIN_EXPECTED_ROWS,
    read_documents: bool = True,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
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

    if read_documents:
        read_dossiers(
            rows,
            fetch_pdf=fetch_pdf,
            pdf_to_text=pdf_to_text,
            delay_seconds=delay_seconds,
        )
    return rows

def scrape_to_wide_csv(
    csv_path: Any, *, delay_seconds: float = 0.25, read_documents: bool = True
) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds, read_documents=read_documents)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

