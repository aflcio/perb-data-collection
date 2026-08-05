"""New Jersey PERC Issued Decisions (Domino).

WHAT THIS FILE IS FOR
---------------------
NJ PERC publishes Issued Decisions in a Lotus Domino NSF view
(percdecisions.nsf / IssuedDecisions). The ReadViewEntries XML feed with
ExpandView returns every decision row (decision number, employer label,
issued datetime, PDF $File link) without clicking year categories in HTML.

Walk that XML with Domino position-based paging (~5k rows historically),
map employer labels into jurisdiction hints, and land through shared
state-PERB ACE (GeoCensus).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_bytes, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NJ PERC Issued Decisions Flow"
REPORT_PREFIX = "nj_perc_issued_decisions"
AGENCY_CODE = "NJ_PERC"
BASE_URL = "https://www.perc.state.nj.us"
VIEW_PATH = "/percdecisions.nsf/IssuedDecisions"
ENTRIES_URL = f"{BASE_URL}{VIEW_PATH}?ReadViewEntries"
PAGE_SIZE = 500

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "decision_year",
    "issued_date",
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

_PDF_HREF_RE = re.compile(
    r'href="([^"]+\.pdf\?OpenElement)"[^>]*>\s*([^<]*?)\s*<',
    flags=re.I,
)
_CASE_RE = re.compile(r"PERC\s+(\d{4})-(\d+)", flags=re.I)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href.lstrip("/"))

def _entrydata_texts(entry: ET.Element, *, name: str | None = None, column: str | None = None) -> list[str]:
    out: list[str] = []
    for ed in entry.findall("entrydata"):
        if name is not None and ed.attrib.get("name") != name:
            continue
        if column is not None and ed.attrib.get("columnnumber") != column:
            continue
        for node in ed.iter():
            if node.tag in {"text", "datetime"} and (node.text or "").strip():
                out.append(node.text.strip())
    return out

def _issued_date(raw: str) -> str:
    # Domino datetime text looks like 20260625T000000,00-04
    compact = re.match(r"^(\d{4})(\d{2})(\d{2})", raw.strip())
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}-{compact.group(3)}"
    return ""

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(r"\s+B/E\s*$", "", name, flags=re.I)
    name = re.sub(r"\s+Board of Education\s*$", "", name, flags=re.I)
    name = re.sub(r"^(City|Town|Township|Borough|County)\s+of\s+", "", name, flags=re.I)
    # "Camden Cty" / "Morris Cty Prosecutor's Office"
    name = re.sub(r"\s+Cty\b.*$", "", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

def parse_viewentries_xml(xml_text: str, *, scraped_at: str) -> tuple[list[dict[str, str]], str | None]:
    """Parse one ReadViewEntries page. Returns (rows, last_position)."""
    root = ET.fromstring(xml_text)
    rows: list[dict[str, str]] = []
    last_position: str | None = None
    current_year = ""

    for entry in root.findall("viewentry"):
        last_position = entry.attrib.get("position") or last_position
        unid = entry.attrib.get("unid")
        category_texts = _entrydata_texts(entry, column="0")
        if not unid:
            for text in category_texts:
                if re.fullmatch(r"\d{4}", text):
                    current_year = text
            continue

        href_blob = " ".join(_entrydata_texts(entry, name="$17") or _entrydata_texts(entry, column="2"))
        href_blob = unescape(href_blob)
        pdf_match = _PDF_HREF_RE.search(href_blob)
        if not pdf_match:
            # Fallback: bare href inside brackets
            href_only = re.search(r'href="([^"]+\.pdf\?OpenElement)"', href_blob, flags=re.I)
            label_only = re.search(r">\s*(PERC[^<]+?)\s*<", href_blob, flags=re.I)
            if not href_only:
                continue
            pdf_href = href_only.group(1)
            case_label = strip_html_text(label_only.group(1) if label_only else "")
        else:
            pdf_href = pdf_match.group(1)
            case_label = strip_html_text(pdf_match.group(2))

        pdf_url = _absolute_url(pdf_href)
        case_number = case_label or f"UNID-{unid[:12]}"
        year = current_year
        case_match = _CASE_RE.search(case_number)
        if case_match:
            year = case_match.group(1)
            case_number = f"PERC {case_match.group(1)}-{int(case_match.group(2)):03d}"

        employer = " ".join(_entrydata_texts(entry, name="$21") or _entrydata_texts(entry, column="5")).strip()
        issued_raw = " ".join(_entrydata_texts(entry, name="IssuedDate")).strip()
        issued_date = _issued_date(issued_raw) if issued_raw else ""

        row_key = f"{AGENCY_CODE}:{unid}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": "ULP",
                "native_case_type": "ISSUED_DECISION",
                "decision_year": year,
                "issued_date": issued_date,
                "employer_name": employer,
                "union_name": "",
                "document_title": case_number,
                "pdf_url": pdf_url,
                "jurisdiction_city": _jurisdiction_city(employer) if employer else "",
                "jurisdiction_state": "NJ",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": ENTRIES_URL,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows, last_position

def scrape_decisions(
    *,
    delay_seconds: float = 0.15,
    fetch_xml: Any = None,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, str]]:
    fetcher = fetch_xml or (
        lambda url, **kwargs: fetch_bytes(url, delay_seconds=kwargs.get("delay_seconds", 0.0)).decode(
            "utf-8", errors="replace"
        )
    )
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    start = "1"
    seen_unids: set[str] = set()
    rows: list[dict[str, str]] = []
    pages = 0

    while True:
        url = f"{ENTRIES_URL}&Start={start}&Count={page_size}&ExpandView"
        xml_text = fetcher(url, delay_seconds=delay_seconds)
        page_rows, last_position = parse_viewentries_xml(xml_text, scraped_at=scraped_at)
        pages += 1
        new_rows = 0
        for row in page_rows:
            unid = row["row_key"].split(":", 1)[-1]
            if unid in seen_unids:
                continue
            seen_unids.add(unid)
            rows.append(row)
            new_rows += 1

        if not last_position or new_rows == 0:
            break
        if last_position == start:
            break
        start = last_position
        if pages > 50:
            break

    if not rows:
        raise RuntimeError(f"NJ PERC IssuedDecisions returned 0 rows from {ENTRIES_URL}")
    rows.sort(key=lambda row: (row["decision_year"], row["case_number"], row["row_key"]), reverse=True)
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.15) -> int:
    rows = scrape_decisions(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

