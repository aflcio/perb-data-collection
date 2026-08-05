"""New Hampshire PELRB bargaining-unit certifications.

WHAT THIS FILE IS FOR
---------------------
Load the PELRB Bargaining Units certification registry harvested from
www.pelrb.nh.gov/bargaining-units (Documents API subcategory 706). Live hosts
are Akamai-blocked from this engineering IP, so the default ingest path reads a
local TSV harvest (`data/NH-PERB/nh_pelrb_certifications.tsv`) rather than
scraping. Title rows embed employer + union; we strip the union taxonomy label
for ACE and set jurisdiction_state=NH.

No Prefect schedule — oneshot / manual reload only (same class as FL PERC).
"""

from __future__ import annotations

import csv
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NH PELRB Certifications Flow"
REPORT_PREFIX = "nh_pelrb_certifications"
AGENCY_CODE = "NH_PELRB"
SOURCE_PAGE_URL = "https://www.pelrb.nh.gov/bargaining-units"
DOCUMENTS_API = (
    "https://www.pelrb.nh.gov/content/api/documents"
    "?iterate_nodes=true&q=%40field_document_subcategory%7C%3D%7C706"
    "&filter_mode=inclusive&type=document"
)
DEFAULT_HARVEST_TSV = Path("data/NH-PERB/nh_pelrb_certifications.tsv")

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "document_id",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "listing_title",
    "certification_date",
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

_TRAILING_UNION_RE = re.compile(
    r"\s+(?:NEA-NH|NHEA/?NEA|NHEA-NEA|NEA|AFSCME|SEA|Teamsters|NEPBA|IAFF|"
    r"AFT|UAW|NCEU|IBEW|IUPE|ICWU|AAUP|NHTA)\s*$",
    flags=re.I,
)

def default_harvest_path() -> Path:
    return Path.cwd() / DEFAULT_HARVEST_TSV

def employer_from_title(title: str, union: str) -> str:
    """Strip the union label from a listing title to recover the employer string."""
    name = " ".join((title or "").split()).strip()
    union_name = " ".join((union or "").split()).strip()
    if union_name and name.upper().endswith(union_name.upper()):
        name = name[: -len(union_name)].rstrip(" -,/\t")
    name = _TRAILING_UNION_RE.sub("", name).rstrip(" -,/\t")
    return name

def jurisdiction_city(employer_name: str) -> str:
    """Best-effort NH town/city token from the employer string (first word)."""
    name = employer_name.strip()
    if not name:
        return ""
    return name.split()[0][:80]

def rows_from_harvest_tsv(
    tsv_path: Path | str,
    *,
    scraped_at: str | None = None,
) -> list[dict[str, str]]:
    path = Path(tsv_path)
    if not path.is_file():
        raise FileNotFoundError(f"NH PELRB harvest TSV not found: {path}")

    scraped = scraped_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"id", "title", "date_posted", "union", "pdf_url", "pdf_filename"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"NH PELRB harvest TSV missing columns {sorted(missing)}: {path}"
            )
        for raw in reader:
            doc_id = (raw.get("id") or "").strip()
            title = (raw.get("title") or "").strip()
            if not doc_id or not title:
                continue
            union_name = (raw.get("union") or "").strip()
            employer_name = employer_from_title(title, union_name)
            pdf_url = (raw.get("pdf_url") or "").strip()
            rows.append(
                {
                    "row_key": f"{AGENCY_CODE}:{doc_id}",
                    "source_agency_code": AGENCY_CODE,
                    "document_id": doc_id,
                    "canonical_case_type": "CERTIFICATION",
                    "native_case_type": "CERTIFICATION",
                    "employer_name": employer_name,
                    "union_name": union_name,
                    "listing_title": title,
                    "certification_date": (raw.get("date_posted") or "").strip(),
                    "jurisdiction_city": jurisdiction_city(employer_name),
                    "jurisdiction_state": "NH",
                    "employer_street": "",
                    "employer_zip": "",
                    "certification_pdf_url": pdf_url,
                    "pdf_file_name": (raw.get("pdf_filename") or "").strip(),
                    "source_page_url": SOURCE_PAGE_URL,
                    "source_url": pdf_url or SOURCE_PAGE_URL,
                    "scraped_at": scraped,
                }
            )
    rows.sort(key=lambda row: int(row["document_id"]))
    return rows

def scrape_certifications(
    *,
    harvest_tsv: Path | str | None = None,
    scraped_at: str | None = None,
) -> list[dict[str, str]]:
    """Load certifications from the local harvest TSV (Akamai blocks live scrape)."""
    path = Path(harvest_tsv) if harvest_tsv else default_harvest_path()
    rows = rows_from_harvest_tsv(path, scraped_at=scraped_at)
    if not rows:
        raise RuntimeError(f"NH PELRB harvest parsed 0 rows: {path}")
    return rows

def scrape_to_wide_csv(
    csv_path: Any,
    *,
    harvest_tsv: Path | str | None = None,
    harvest_path: Path | str | None = None,
) -> int:
    rows = scrape_certifications(harvest_tsv=harvest_tsv or harvest_path)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

