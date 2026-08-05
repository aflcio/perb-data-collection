"""Minnesota BMS exclusive-rep certifications.

WHAT THIS FILE IS FOR
---------------------
Load Order-Certification of Excl Rep listing rows harvested from
mn.gov/bms/search (json.jsp / Search All Documents). Live search is often
bot-gated, so the default ingest path reads a local harvest JSONL rather
than scraping live. Pass ``--harvest`` / ``harvest_jsonl`` explicitly.

Oneshot / manual reload (same class as NH PELRB / FL PERC).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "MN BMS Certifications Flow"
REPORT_PREFIX = "mn_bms_certifications"
AGENCY_CODE = "MN_BMS"
SOURCE_PAGE_URL = "https://mn.gov/bms/search/"
SEARCH_JSON = "https://mn.gov/bms/search/json.jsp"
DEFAULT_HARVEST_JSONL = Path("data/MN-BMS/mn_bms_certifications.jsonl")
DOC_CLASS = "Order-Certification of Excl Rep"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "document_id",
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
    "certification_pdf_url",
    "pdf_file_name",
    "source_page_url",
    "source_url",
    "scraped_at",
)

def default_harvest_path() -> Path:
    return Path.cwd() / DEFAULT_HARVEST_JSONL

def _normalize_date(raw: str | None) -> str:
    """Prefer YYYY-MM-DD from ISO-ish or leave a trimmed raw string."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "T" in text:
        return text.split("T", 1)[0][:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return text

def jurisdiction_city(employer_name: str) -> str:
    """Best-effort MN place token from the employer listing string."""
    name = " ".join((employer_name or "").split()).strip()
    if not name:
        return ""

    city_of = re.match(r"^(?:City|Town|Township|Village)\s+of\s+(.+)$", name, flags=re.I)
    if city_of:
        place = city_of.group(1).strip()
        return place.split(",")[0].strip()[:80]

    county = re.match(r"^(.+?)\s+County\b", name, flags=re.I)
    if county and not name.lower().startswith("state of"):
        return county.group(1).strip()[:80]

    isd = re.match(
        r"^ISD\s+\d[\dA-Za-z\-]*\s*[,\-–]\s*(.+)$",
        name,
        flags=re.I,
    )
    if isd:
        return isd.group(1).strip().split(",")[0].strip()[:80]

    # "Independent School District No. 238, Mabel-Canton"
    isd_long = re.search(r",\s*([^,]+)$", name)
    if isd_long and re.search(r"school|district|education", name, flags=re.I):
        return isd_long.group(1).strip()[:80]

    return name.split(",")[0].strip().split()[0][:80]

def _pdf_file_name(pdf_url: str) -> str:
    if not pdf_url:
        return ""
    path = unquote(urlparse(pdf_url).path)
    return path.rsplit("/", 1)[-1]

def _prefer_pdf_url(raw: dict[str, Any]) -> str:
    pdf = (raw.get("pdf_url") or "").strip()
    if "documents2" in pdf:
        return pdf
    caseload = (raw.get("caseload_pdf_url") or "").strip()
    if pdf:
        return pdf
    return caseload

def rows_from_harvest_jsonl(
    jsonl_path: Path | str,
    *,
    scraped_at: str | None = None,
) -> list[dict[str, str]]:
    path = Path(jsonl_path)
    if not path.is_file():
        raise FileNotFoundError(f"MN BMS harvest JSONL not found: {path}")

    scraped = scraped_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    by_id: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {path}") from exc
            if not isinstance(raw, dict):
                continue
            doc_id = str(raw.get("document_id") or "").strip()
            if not doc_id:
                continue
            employer_name = (raw.get("employer_name") or "").strip()
            pdf_url = _prefer_pdf_url(raw)
            title = (raw.get("title") or raw.get("document_title") or "").strip()
            row = {
                "row_key": f"{AGENCY_CODE}:{doc_id}",
                "source_agency_code": AGENCY_CODE,
                "document_id": doc_id,
                "case_number": (raw.get("case_number") or "").strip(),
                "canonical_case_type": "CERTIFICATION",
                "native_case_type": (raw.get("doc_class") or DOC_CLASS).strip(),
                "employer_name": employer_name,
                "union_name": (raw.get("union_name") or "").strip(),
                "document_title": title,
                "decision_date": _normalize_date(
                    raw.get("date") or raw.get("date_raw") or raw.get("decision_date")
                ),
                "jurisdiction_city": jurisdiction_city(employer_name),
                "jurisdiction_state": "MN",
                "employer_street": "",
                "employer_zip": "",
                "certification_pdf_url": pdf_url,
                "pdf_file_name": _pdf_file_name(pdf_url),
                "source_page_url": SOURCE_PAGE_URL,
                "source_url": pdf_url or SOURCE_PAGE_URL,
                "scraped_at": scraped,
            }
            # Prefer rows with employer + documents2 URL when duplicates appear.
            existing = by_id.get(doc_id)
            if existing is None:
                by_id[doc_id] = row
                continue
            better = (
                (not existing["employer_name"] and row["employer_name"])
                or (
                    "documents2" in row["certification_pdf_url"]
                    and "documents2" not in existing["certification_pdf_url"]
                )
            )
            if better:
                by_id[doc_id] = row

    rows = list(by_id.values())
    rows.sort(key=lambda row: int(row["document_id"]) if row["document_id"].isdigit() else 0)
    return rows

def scrape_certifications(
    *,
    harvest_jsonl: Path | str | None = None,
    scraped_at: str | None = None,
) -> list[dict[str, str]]:
    """Load certifications from the local harvest JSONL (search CAPTCHA blocks live scrape)."""
    path = Path(harvest_jsonl) if harvest_jsonl else default_harvest_path()
    rows = rows_from_harvest_jsonl(path, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"MN BMS harvest parsed 0 rows: {path}")
    return rows

def scrape_to_wide_csv(
    csv_path: Any,
    *,
    harvest_jsonl: Path | str | None = None,
    harvest_path: Path | str | None = None,
) -> int:
    rows = scrape_certifications(harvest_jsonl=harvest_jsonl or harvest_path)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

