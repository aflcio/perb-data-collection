"""Vermont VLRB volume-zip decision index.

WHAT THIS FILE IS FOR
---------------------
Download VLRB decision volume ZIP archives listed on
vlrb.vermont.gov/decisions/download (Volumes 1–34 direct .zip links), index each
embedded PDF filename for citation/parties without OCR, then write a wide CSV.

Volumes 35+ are Drupal document nodes (not flat zips) and are skipped until a
stable direct-zip URL appears. Monthly cadence — archives change slowly.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url, fetch_bytes
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "VT VLRB Volume Decisions Flow"
REPORT_PREFIX = "vt_vlrb_volume_decisions"
AGENCY_CODE = "VT_VLRB"
BASE_URL = "https://vlrb.vermont.gov"
DOWNLOAD_URL = f"{BASE_URL}/decisions/download"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "volume_number",
    "volume_label",
    "employer_name",
    "union_name",
    "document_title",
    "pdf_name",
    "source_zip_url",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_VOLUME_ZIP_RE = re.compile(
    r'href="([^"]*Volume(?:%20|\s|_)?(?P<num>\d+)\.zip)"[^>]*>\s*'
    r"(?P<label>Volume\s+\d+[^<]*)",
    flags=re.I,
)
# 34-207 Rutland EA v. Rutland Sch. Bd.pdf
_NAME_RE = re.compile(
    r"^(?P<vol>\d+)-(?P<page>\d+(?:-\d+)?)\s*(?P<rest>.*?)(?:\.pdf)?$",
    flags=re.I,
)
# Filenames often encode grievances as "Gr. of <tail>". When <tail> is a
# surname, putting it in union_name mislabels a private individual as a union
# (infra-35). Keep only tails that look like real bargaining agents.
_GR_OF_RE = re.compile(r"^Gr\.?\s+of\s+(?P<tail>.+)$", flags=re.I)
_UNIONISH_RE = re.compile(
    r"\b("
    r"VSEA|VSCFF|AFSCME|IBEW|NEA|AFT|CWA|IAFF|SEIU|UE|NAGE|"
    r"Teamsters|Local\s+\d+|Council\s+\d+|"
    r"Ass(?:ocia)?(?:'?n|tion)|Union|Federation|Guild|Brotherhood"
    r")\b",
    flags=re.I,
)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def list_volume_zips(html: str) -> list[tuple[str, str, str]]:
    """Return (volume_number, zip_url, label) for direct .zip volume links."""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in _VOLUME_ZIP_RE.finditer(html):
        num = match.group("num")
        if num in seen:
            continue
        seen.add(num)
        found.append(
            (
                num,
                _absolute_url(match.group(1)),
                re.sub(r"\s+", " ", match.group("label")).strip(),
            )
        )
    found.sort(key=lambda item: int(item[0]))
    return found

def _looks_like_union(name: str) -> bool:
    return bool(_UNIONISH_RE.search(name))

def _parties_from_rest(rest: str) -> tuple[str, str]:
    text = rest.strip()
    text = re.sub(r"\s+", " ", text)
    # Grievance filings — caption stays in document_title; union only when
    # the grievant-side string is actually a union (e.g. "Gr. of VSEA").
    gr_match = _GR_OF_RE.match(text)
    if gr_match:
        tail = gr_match.group("tail").strip()
        if _looks_like_union(tail):
            return "State of Vermont", text
        return "State of Vermont", ""
    for sep in (" v. ", " v ", " and "):
        if sep in text:
            left, right = text.split(sep, 1)
            left, right = left.strip(), right.strip()
            # School boards / towns are usually employers on the right of "v."
            if sep.startswith(" v"):
                return right, left
            # "Union and Employer"
            return right, left
    return text, ""

def _canonical_from_title(title: str) -> str:
    lowered = title.lower()
    if "decertif" in lowered:
        return "DECERTIFICATION"
    if any(k in lowered for k in ("unit", "represent", "election", "certif", "bargain")):
        return "CERTIFICATION"
    if "gr." in lowered or "grievance" in lowered or "appeal" in lowered:
        return "ARBITRATION"
    return "ARBITRATION"

def parse_pdf_name(
    pdf_name: str,
    *,
    volume_number: str,
    volume_label: str,
    zip_url: str,
    scraped_at: str,
) -> dict[str, str]:
    base = unquote(pdf_name.rsplit("/", 1)[-1])
    stem = re.sub(r"\.pdf$", "", base, flags=re.I)
    match = _NAME_RE.match(stem)
    if match:
        vol = match.group("vol")
        page = match.group("page")
        rest = match.group("rest").strip(" -_")
        case_number = f"{vol}-{page}"
        employer, union = _parties_from_rest(rest)
        title = stem
    else:
        vol = volume_number
        page = ""
        case_number = stem[:80]
        employer, union = _parties_from_rest(stem)
        title = stem
        rest = stem

    if not employer:
        employer = rest or f"VLRB Volume {volume_number}"

    return {
        "row_key": f"{AGENCY_CODE}:{case_number}:{base[:80]}",
        "source_agency_code": AGENCY_CODE,
        "case_number": case_number,
        "canonical_case_type": _canonical_from_title(title),
        "native_case_type": "VLRB_VOLUME",
        "volume_number": vol or volume_number,
        "volume_label": volume_label,
        "employer_name": employer,
        "union_name": union,
        "document_title": title,
        "pdf_name": base,
        "source_zip_url": zip_url,
        "jurisdiction_city": "",
        "jurisdiction_state": "VT",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": DOWNLOAD_URL,
        "source_url": zip_url,
        "scraped_at": scraped_at,
    }

def list_pdf_names_from_zip(zip_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        return [
            name
            for name in archive.namelist()
            if name.lower().endswith(".pdf") and not name.endswith("/")
        ]

def scrape_volume_decisions(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    fetch_zip: Any = None,
) -> list[dict[str, str]]:
    html_fetcher = fetch_html or fetch_url
    zip_fetcher = fetch_zip or fetch_bytes
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = html_fetcher(DOWNLOAD_URL, delay_seconds=delay_seconds)
    volumes = list_volume_zips(html)
    if not volumes:
        raise RuntimeError(f"No direct VLRB volume ZIP links on {DOWNLOAD_URL}")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for volume_number, zip_url, label in volumes:
        zip_bytes = zip_fetcher(zip_url, delay_seconds=delay_seconds)
        for pdf_name in list_pdf_names_from_zip(zip_bytes):
            row = parse_pdf_name(
                pdf_name,
                volume_number=volume_number,
                volume_label=label,
                zip_url=zip_url,
                scraped_at=scraped_at,
            )
            if row["row_key"] in seen:
                continue
            seen.add(row["row_key"])
            rows.append(row)

    if not rows:
        raise RuntimeError("VLRB volume ZIPs contained 0 PDF decision files")
    rows.sort(
        key=lambda row: (
            int(row["volume_number"] or 0),
            row["case_number"],
            row["pdf_name"],
        )
    )
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_volume_decisions(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

