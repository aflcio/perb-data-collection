"""Oregon ERB Final Orders (ContentDM).

WHAT THIS FILE IS FOR
---------------------
Oregon Employment Relations Board final orders live in OCLC ContentDM collection
p17027coll9. Paginate the dmQuery JSON API for title / date / case name / type,
split parties from the Official Case Name (`subjec`), map ERB case-type labels
into the shared canonical_case_type enum, then run shared state-PERB ACE
(GeoCensus). Cadence is monthly — the archive is large (~4.8k+ orders).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from perb_data_collection.http import fetch_url
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "OR ERB ContentDM Orders Flow"
REPORT_PREFIX = "or_erb_contentdm_orders"
AGENCY_CODE = "OR_ERB"
COLLECTION = "p17027coll9"
CDM_HOST = "https://cdm17027.contentdm.oclc.org"
QUERY_FIELDS = "title!date!descri!subjec!type!identi"
PAGE_SIZE = 200

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "document_title",
    "official_case_name",
    "decision_date",
    "contentdm_pointer",
    "pdf_url",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_CASE_FROM_TITLE_RE = re.compile(
    r"^([A-Z]{1,4}-\d{1,4}(?:-\d{2,4})?)\b",
    flags=re.I,
)
_TYPE_CANONICAL = (
    (re.compile(r"unit clarification|representation", re.I), "UNIT_CLARIFICATION"),
    (re.compile(r"unfair labor practice|ulp", re.I), "ULP"),
    (re.compile(r"declaratory", re.I), "NEGOTIABILITY"),
    (re.compile(r"arbitration|interest|impasse", re.I), "ARBITRATION"),
    (re.compile(r"representation costs|attorney fees", re.I), "ULP"),
    (re.compile(r"personnel relations|sprl", re.I), "ULP"),
    (re.compile(r"certif", re.I), "CERTIFICATION"),
    (re.compile(r"decertif", re.I), "DECERTIFICATION"),
)

def _query_url(*, start: int, maxrecs: int = PAGE_SIZE) -> str:
    q = (
        f"dmQuery/{COLLECTION}/0/{QUERY_FIELDS}/dated/"
        f"{maxrecs}/{start}/1/0/0/0/0/0/json"
    )
    return f"{CDM_HOST}/digital/bl/dmwebservices/index.php?q={quote(q, safe='/')}"

def _item_page_url(pointer: str | int) -> str:
    return f"{CDM_HOST}/digital/collection/{COLLECTION}/id/{pointer}"

def _pdf_url(pointer: str | int) -> str:
    return f"{CDM_HOST}/digital/api/collection/{COLLECTION}/id/{pointer}/download"

def _canonical(native_type: str, title: str) -> str:
    blob = f"{native_type} {title}"
    for pattern, canonical in _TYPE_CANONICAL:
        if pattern.search(blob):
            return canonical
    return "ULP"

def _parties(official_case_name: str) -> tuple[str, str]:
    """Split 'A v. B' style Case Name into (employer, union) heuristically."""
    text = re.sub(r"\s+", " ", official_case_name).strip()
    if not text:
        return "", ""
    match = re.search(r"\s+v\.?\s+", text, flags=re.I)
    if not match:
        return text, ""
    left = text[: match.start()].strip(" ,;")
    right = text[match.end() :].strip(" ,;")
    employer_hints = (
        "city",
        "county",
        "district",
        "state",
        "school",
        "university",
        "college",
        "town",
        "borough",
        "metro",
        "hospital",
        "commission",
        "authority",
        "bureau",
        "department",
        "fire and rescue",
    )
    left_emp = any(h in left.lower() for h in employer_hints)
    right_emp = any(h in right.lower() for h in employer_hints)
    if right_emp and not left_emp:
        return right, left
    if left_emp and not right_emp:
        return left, right
    # Default: first party petitioner/charging party; prefer right as employer
    # when neither side looks public (individual vs local).
    return right if right_emp or not left_emp else left, left if right_emp or not left_emp else right

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(r"^(City|Town|County|Borough)\s+of\s+", "", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

def _case_number(title: str, official: str) -> str:
    for blob in (title, official):
        match = _CASE_FROM_TITLE_RE.match(blob.strip())
        if match:
            return match.group(1).upper()
    match = re.search(r"\b([A-Z]{1,4}-\d{1,4}(?:-\d{2,4})?)\b", title, flags=re.I)
    if match:
        return match.group(1).upper()
    return re.sub(r"[^A-Za-z0-9]+", "-", title)[:40].strip("-")

def parse_query_page(payload: dict[str, Any], *, scraped_at: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rec in payload.get("records") or []:
        pointer = str(rec.get("pointer", "")).strip()
        if not pointer:
            continue
        title = str(rec.get("title") or "").strip()
        official = str(rec.get("subjec") or "").strip()
        native = str(rec.get("type") or "").strip() or "ORDER"
        decision_date = str(rec.get("date") or "").strip()
        case_number = _case_number(title, official)
        employer, union = _parties(official)
        pdf_url = _pdf_url(pointer)
        item_url = _item_page_url(pointer)
        row_key = f"{AGENCY_CODE}:{pointer}:{case_number}"
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "canonical_case_type": _canonical(native, title),
                "native_case_type": native,
                "employer_name": employer,
                "union_name": union,
                "document_title": title,
                "official_case_name": official,
                "decision_date": decision_date,
                "contentdm_pointer": pointer,
                "pdf_url": pdf_url,
                "jurisdiction_city": _jurisdiction_city(employer),
                "jurisdiction_state": "OR",
                "employer_street": "",
                "employer_zip": "",
                "source_page_url": item_url,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_orders(
    *,
    delay_seconds: float = 0.15,
    fetch_json: Any = None,
    page_size: int = PAGE_SIZE,
) -> list[dict[str, str]]:
    """Paginate ContentDM dmQuery until all Final Order records are collected."""
    fetcher = fetch_json or (lambda url, **kwargs: fetch_url(url, **kwargs))
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    start = 1
    total: int | None = None
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    while True:
        url = _query_url(start=start, maxrecs=page_size)
        raw = fetcher(url, delay_seconds=delay_seconds)
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if total is None:
            total = int(payload.get("pager", {}).get("total") or 0)
        page_rows = parse_query_page(payload, scraped_at=scraped_at)
        if not page_rows:
            break
        for row in page_rows:
            if row["contentdm_pointer"] in seen:
                continue
            seen.add(row["contentdm_pointer"])
            rows.append(row)
        start += page_size
        if total is not None and start > total:
            break
        # Safety: empty page or API stopped returning new rows
        if len(page_rows) < page_size and (total is None or len(rows) >= total):
            break

    if not rows:
        raise RuntimeError("OR ERB ContentDM dmQuery returned 0 Final Order records")
    if total is not None and len(rows) < total * 0.95:
        raise RuntimeError(
            f"OR ERB ContentDM scrape incomplete: got {len(rows)} of {total} records"
        )
    rows.sort(key=lambda row: (row["decision_date"], row["case_number"], row["contentdm_pointer"]))
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.15) -> int:
    rows = scrape_orders(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

