"""Hawaii HLRB HRS Chapter 89 employee-organization certifications

WHAT THIS FILE IS FOR
---------------------
HLRB hosts a short PDF roster of exclusive representatives and statewide
bargaining units under HRS Chapter 89 (unit number, certification date, HQ
address). Discover the current "List of Employee Organizations" PDF from the
hlrb home page, emit one row per exclusive-representative×unit, then run
shared state-PERB ACE (GeoCensus) using the union HQ street when present
(statewide employer = State of Hawaii; city/state HI).
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

FLOW_NAME = "HI HLRB Employee Organizations Flow"
REPORT_PREFIX = "hi_hlrb_employee_orgs"
AGENCY_CODE = "HI_HLRB"
BASE_URL = "https://labor.hawaii.gov"
HOME_URL = f"{BASE_URL}/hlrb/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "bargaining_unit_name",
    "unit_number",
    "certification_date",
    "recertified",
    "contact_name",
    "contact_title",
    "union_phone",
    "union_website",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_PDF_HREF_RE = re.compile(
    r'href="([^"]*List-of-Employee-Organizations[^"]*\.pdf)"',
    flags=re.I,
)
_PDF_HREF_FALLBACK_RE = re.compile(
    r'href="([^"]*Employee-Organizations[^"]*\.pdf)"',
    flags=re.I,
)
# Dual-column: left org text, right "Unit N (label) date"
_UNIT_INLINE_RE = re.compile(
    r"Unit\s+(?P<num>\d+)\s*\((?P<label>[^)]+)\)\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\*?",
    flags=re.I,
)
_UNIT_OPEN_RE = re.compile(
    r"Unit\s+(?P<num>\d+)\s*\((?P<label>[^)]*?)\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\*?\s*$",
    flags=re.I,
)
_UNIT_CLOSE_RE = re.compile(r"^\s*(?P<label>[^)]+)\)\s*$")
_ADDR_RE = re.compile(
    r"(?P<street>\d+[^,]+),\s*(?P<city>[A-Za-z .]+),\s*"
    r"(?:Hawaii|HI)\s+(?P<zip>\d{5}(?:-\d{4})?)",
    flags=re.I,
)
_PHONE_RE = re.compile(r"Tel\.\s*(.+)$", flags=re.I)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", flags=re.I)
_HEADER_RE = re.compile(
    r"HRS CHAPTER 89|EMPLOYEE ORGANIZATIONS|EXCLUSIVE REPRESENTATIVE|"
    r"BARGAINING UNIT|DATE OF|CERTIFICATION|Last update:|Recertified as",
    flags=re.I,
)
_TITLE_RE = re.compile(
    r"^(President|Executive Director|State Director|General Manager|Director)$",
    flags=re.I,
)
_ORG_START_RE = re.compile(
    r"^(HAWAII FIRE FIGHTERS|HAWAII GOVERNMENT EMPLOYEES|HAWAII STATE TEACHERS|"
    r"STATE OF HAWAII ORGANIZATION OF|UNITED PUBLIC WORKERS|UNIVERSITY OF HAWAII)\b",
    flags=re.I,
)

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
                "pdftotext is required to parse HI HLRB employee-organization PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftotext failed: {exc.stderr or exc.stdout or exc}"
            ) from exc
        return completed.stdout

def discover_orgs_pdf_url(html: str) -> str:
    match = _PDF_HREF_RE.search(html) or _PDF_HREF_FALLBACK_RE.search(html)
    if not match:
        raise RuntimeError(
            f"No List-of-Employee-Organizations PDF linked from {HOME_URL}"
        )
    return _absolute_url(match.group(1))

def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
    return slug[:80] or "UNKNOWN"

def _clean(value: str) -> str:
    text = (
        value.replace("\xa0", " ")
        .replace("\u02bb", "'")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    return re.sub(r"\s+", " ", text).strip()

def _left_column(line: str) -> str:
    """Return roughly the left (exclusive-rep) column text."""
    # Unit column usually starts after a wide gap
    parts = re.split(r"\s{2,}", line.strip(), maxsplit=1)
    if not parts:
        return ""
    left = parts[0]
    # Strip any unit text that leaked into a single-chunk line
    left = _UNIT_INLINE_RE.sub("", left)
    left = re.sub(r"Unit\s+\d+\s*\([^)]*$", "", left, flags=re.I)
    return _clean(left)

def parse_orgs_text(
    text: str,
    *,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    """Parse pdftotext layout into one row per exclusive-rep × unit."""
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pending_open: dict[str, str] | None = None
    city_zip_re = re.compile(
        r"^(?P<city>[A-Za-z .]+),\s*(?:Hawaii|HI)\s+(?P<zip>\d{5}(?:-\d{4})?)\s*$",
        flags=re.I,
    )

    def start_block(seed: str) -> None:
        nonlocal current
        current = {
            "name_parts": [seed],
            "contact_name": "",
            "contact_title": "",
            "street": "",
            "city": "Honolulu",
            "zip": "",
            "phone": "",
            "website": "",
            "units": [],
        }
        blocks.append(current)

    for raw in text.splitlines():
        if not raw.strip() or _HEADER_RE.search(raw):
            pending_open = None
            continue
        if set(raw.strip()) <= {"_", "-"}:
            continue

        left = _left_column(raw)
        org_started = False
        # Start block before binding units so "ORG … Unit N" attaches correctly.
        if left and _ORG_START_RE.match(left):
            start_block(left)
            pending_open = None
            org_started = True

        if pending_open and current is not None:
            close = _UNIT_CLOSE_RE.match(raw)
            if close:
                label = _clean(f"{pending_open['label']} {close.group('label')}")
                current["units"].append(
                    (
                        pending_open["num"],
                        label,
                        pending_open["date"],
                        pending_open["recert"],
                    )
                )
                pending_open = None
                continue

        open_match = _UNIT_OPEN_RE.search(raw)
        inline_units = list(_UNIT_INLINE_RE.finditer(raw))
        if inline_units:
            if current is not None:
                for match in inline_units:
                    full = match.group(0)
                    current["units"].append(
                        (
                            match.group("num"),
                            _clean(match.group("label")),
                            match.group("date"),
                            full.rstrip().endswith("*"),
                        )
                    )
            pending_open = None
        elif open_match and current is not None:
            pending_open = {
                "num": open_match.group("num"),
                "label": open_match.group("label").strip(),
                "date": open_match.group("date"),
                "recert": bool(re.search(r"\*", raw[open_match.start() :])),
            }

        if not left or current is None:
            continue

        if org_started:
            # Seed name already stored; do not append again.
            continue

        if (
            not current["contact_name"]
            and not current["street"]
            and not _ORG_START_RE.match(left)
            and (
                left.isupper()
                or re.search(
                    r"LOCAL\s+\d+|AFL-CIO|ASSOCIATION|ASSEMBLY|POLICE OFFICERS|"
                    r"PROFESSIONAL ASSEMBLY|"
                    r"\(HFFA\)|\(HGEA\)|\(HSTA\)|\(SHOPO\)|\(UPW\)|\(UHPA\)",
                    left,
                    flags=re.I,
                )
            )
            and not _TITLE_RE.match(left)
            and not _ADDR_RE.search(left)
            and not city_zip_re.match(left)
            and not _PHONE_RE.match(left)
            and not _URL_RE.search(left)
        ):
            current["name_parts"].append(left)
            continue

        addr = _ADDR_RE.search(left)
        if addr:
            current["street"] = _clean(addr.group("street"))
            current["city"] = _clean(addr.group("city"))
            current["zip"] = addr.group("zip")
            continue

        city_zip = city_zip_re.match(left)
        if city_zip:
            current["city"] = _clean(city_zip.group("city"))
            current["zip"] = city_zip.group("zip")
            continue

        phone = _PHONE_RE.search(left)
        if phone:
            current["phone"] = _clean(phone.group(1))
            continue

        url = _URL_RE.search(left)
        if url:
            current["website"] = url.group(0).rstrip("/")
            continue

        if _TITLE_RE.match(left):
            current["contact_title"] = left
            continue

        if re.match(r"^\d+\s+\S+", left) and "Hawaii" not in left:
            current["street"] = left
            continue

        if not current["contact_name"] and re.match(r"^[A-Z][\w.''\s-]+$", left):
            if not _ORG_START_RE.match(left) and "ASSOCIATION" not in left.upper():
                current["contact_name"] = left

    rows: list[dict[str, str]] = []
    for block in blocks:
        union_name = _clean(" ".join(block["name_parts"]))
        for unit_num, unit_label, cert_date, recertified in block["units"]:
            zipcode = block["zip"]
            rows.append(
                {
                    "row_key": f"{AGENCY_CODE}:UNIT_{unit_num}:{_slug(union_name)}",
                    "source_agency_code": AGENCY_CODE,
                    "canonical_case_type": "CERTIFICATION",
                    "native_case_type": "HRS89_EMPLOYEE_ORG",
                    "employer_name": "State of Hawaii",
                    "union_name": union_name,
                    "bargaining_unit_name": f"Unit {unit_num} ({unit_label})",
                    "unit_number": unit_num,
                    "certification_date": cert_date,
                    "recertified": "Y" if recertified else "N",
                    "contact_name": block["contact_name"],
                    "contact_title": block["contact_title"],
                    "union_phone": block["phone"],
                    "union_website": block["website"],
                    "jurisdiction_city": block["city"] or "Honolulu",
                    "jurisdiction_state": "HI",
                    "employer_street": block["street"],
                    "employer_zip": zipcode.split("-")[0] if zipcode else "",
                    "source_pdf_url": pdf_url,
                    "source_page_url": HOME_URL,
                    "source_url": pdf_url,
                    "scraped_at": scraped_at,
                }
            )

    if not rows:
        raise RuntimeError("HI HLRB employee-organizations PDF parsed 0 units")
    rows.sort(key=lambda row: (int(row["unit_number"]), row["union_name"]))
    return rows

def scrape_employee_orgs(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    fetch_pdf: Any = None,
    parse_text: Any = None,
) -> list[dict[str, str]]:
    html_fetcher = fetch_html or fetch_url
    pdf_fetcher = fetch_pdf or fetch_bytes
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = html_fetcher(HOME_URL, delay_seconds=delay_seconds)
    pdf_url = discover_orgs_pdf_url(html)
    pdf_bytes = pdf_fetcher(pdf_url, delay_seconds=delay_seconds)
    text = parse_text(pdf_bytes) if parse_text else _pdf_to_text(pdf_bytes)
    return parse_orgs_text(text, pdf_url=pdf_url, scraped_at=scraped_at)

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_employee_orgs(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

