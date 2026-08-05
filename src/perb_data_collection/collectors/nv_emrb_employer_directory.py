"""Nevada EMRB local-government employer directory

WHAT THIS FILE IS FOR
---------------------
EMRB publishes an annual "State Government and Local Government Data" PDF with
employer addresses and (where known) association/union + bargaining unit.
Discover the current PDF from the agency homepage, parse one row per
employer×union×unit relationship, then write a wide CSV.

Addresses are the win for ACE here — city/state/ZIP are explicit NV locals.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse, unquote

from perb_data_collection.http import fetch_url, fetch_bytes
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NV EMRB Employer Directory Flow"
REPORT_PREFIX = "nv_emrb_employer_directory"
AGENCY_CODE = "NV_EMRB"
BASE_URL = "https://emrb.nv.gov"
HOME_URL = f"{BASE_URL}/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "bargaining_unit_name",
    "contact_name",
    "contact_email",
    "contact_phone",
    "website",
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
    r'href="([^"]*Local\s*Government\s*Employer\s*Data[^"]*\.pdf)"',
    flags=re.I,
)
_PDF_HREF_FALLBACK_RE = re.compile(
    r'href="([^"]*Employer\s*Data[^"]*\.pdf)"',
    flags=re.I,
)
_PRIMARY_RE = re.compile(
    r"^(?P<left>.+?)\s+NV\s+(?P<zip>\d{5})\s*(?P<right>.*)$"
)
_PHONE_RE = re.compile(
    r"^(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?:\s+Ext\.?\s*\d+)?)\s*(.*)$",
    flags=re.I,
)
_PAGE_FOOTER_RE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", flags=re.I)
_SKIP_LINE_RE = re.compile(
    r"STATE GOVERNMENT and LOCAL GOVERNMENT DATA|LOCAL GOVERNMENT\s*$|"
    r"First Name\s+Last Name|GOVERNMENT\s+First Name",
    flags=re.I,
)

def _absolute_url(href: str) -> str:
    """Join to BASE_URL and percent-encode spaces in the path (http.client forbids them)."""
    joined = urljoin(BASE_URL + "/", unquote(href.replace("&amp;", "&")))
    parsed = urlparse(joined)
    encoded_path = quote(parsed.path, safe="/")
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            encoded_path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

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
                "pdftotext is required to parse NV EMRB employer-directory PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftotext failed: {exc.stderr or exc.stdout or exc}"
            ) from exc
        return completed.stdout

def discover_employer_pdf_url(html: str) -> str:
    match = _PDF_HREF_RE.search(html) or _PDF_HREF_FALLBACK_RE.search(html)
    if not match:
        raise RuntimeError(
            f"No Local Government Employer Data PDF linked from {HOME_URL}"
        )
    return _absolute_url(match.group(1))

def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
    return slug[:80] or "UNKNOWN"

def _clean(value: str) -> str:
    text = (
        value.replace("\xa0", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("'", "'")
        .replace("'", "'")
    )
    return re.sub(r"\s+", " ", text).strip()

def _looks_like_website(value: str) -> bool:
    lowered = value.lower().strip().rstrip(".")
    if lowered in {"n/a", "none", ".", "-"}:
        return False
    return bool(
        lowered.startswith("www.")
        or lowered.startswith("http")
        or (
            "." in lowered
            and " " not in lowered
            and "@" not in lowered
            and not lowered.startswith("unit ")
        )
    )

def _parse_tail(right: str) -> tuple[str, str, str, str, str]:
    """Return phone, email, union, unit, website from the post-ZIP remainder."""
    phone = ""
    rest = right.strip()
    phone_match = _PHONE_RE.match(rest)
    if phone_match:
        phone = phone_match.group(1).strip()
        rest = phone_match.group(2).strip()

    parts = [p for p in re.split(r"\s{2,}", rest) if p.strip()]
    email = ""
    if parts and "@" in parts[0]:
        email = parts.pop(0).strip()

    website = ""
    if parts and _looks_like_website(parts[-1]):
        website = parts.pop(-1).strip()

    union = ""
    unit = ""
    if parts:
        first = parts[0].strip()
        if first.lower() == "none":
            union = ""
            parts = parts[1:]
        else:
            union = first
            parts = parts[1:]
        if parts:
            unit = parts[0].strip()
            # Phone/email leakage into unit when columns collapse
            if re.match(r"^\(?\d{3}\)?", unit) or "@" in unit:
                unit = ""
    return phone, email, _clean(union), _clean(unit), website

def _parse_primary_line(line: str) -> dict[str, str] | None:
    match = _PRIMARY_RE.match(line)
    if not match:
        return None
    left = match.group("left").rstrip()
    zipcode = match.group("zip")
    right = match.group("right").strip()
    parts = [p for p in re.split(r"\s{2,}", left.strip()) if p]
    if len(parts) < 3:
        return None

    if len(parts) >= 5:
        employer = " ".join(parts[:-4]).strip()
        first, last, street, city = parts[-4], parts[-3], parts[-2], parts[-1]
    elif len(parts) == 4:
        # Usually: employer | first | street | city  (last-name column collapsed)
        employer, first, street, city = parts
        last = ""
        if not re.search(
            r"\d|Box|Street|St\.|Drive|Dr\.|Road|Rd\.|Ave|Lane|Way|Pkwy|Route",
            street,
            flags=re.I,
        ):
            # employer | first | last | city  (address missing)
            last = street
            street = ""
    else:
        employer = parts[0]
        first = parts[1] if len(parts) > 2 else ""
        last = ""
        street = parts[-2] if len(parts) >= 3 else ""
        city = parts[-1]

    # Fix "… Nevada Ryan" / "… Medical Melissa" first-name glued to employer
    glued = re.match(
        r"^(?P<emp>.+?)\s+(?P<first>Ryan|Melissa|Autumn|Shari(?:\s+L\.)?)$",
        employer,
        flags=re.I,
    )
    if glued and first and not last:
        employer = glued.group("emp")
        last = first
        first = glued.group("first")

    phone, email, union, unit, website = _parse_tail(right)
    contact = _clean(f"{first} {last}")
    return {
        "employer_name": _clean(employer),
        "contact_name": contact,
        "employer_street": _clean(street),
        "jurisdiction_city": _clean(city),
        "employer_zip": zipcode,
        "contact_phone": phone,
        "contact_email": email,
        "union_name": union,
        "bargaining_unit_name": unit,
        "website": website,
    }

def _parse_continuation(line: str) -> tuple[str, str] | None:
    """Union/unit continuation under a primary employer (no NV ZIP)."""
    if not line.startswith(" ") and not line.startswith("\t"):
        return None
    stripped = line.strip()
    if not stripped or _PAGE_FOOTER_RE.match(stripped) or _SKIP_LINE_RE.search(stripped):
        return None
    if re.search(r"\bNV\s+\d{5}\b", stripped):
        return None
    # Skip extra contact emails / phone-only leftovers
    if stripped.startswith("also ") or stripped.startswith("ext "):
        return None
    if "@" in stripped and " " not in stripped.split("@")[0][-20:]:
        # lone email line
        if len(stripped.split()) <= 2 and "@" in stripped:
            return None
    parts = [p for p in re.split(r"\s{2,}", stripped) if p.strip()]
    if not parts:
        return None
    # Drop leading parenthetical fragments like "(BFFA)"
    if len(parts) == 1 and parts[0].startswith("(") and parts[0].endswith(")"):
        return None
    union = _clean(parts[0])
    unit = _clean(parts[1]) if len(parts) >= 2 else ""
    if union.lower() in {"none", "n/a", "."}:
        return None
    if re.match(r"^\(?\d{3}\)?", union):
        return None
    return union, unit

def parse_employer_text(
    text: str,
    *,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    """Parse pdftotext -layout output into employer×union×unit rows."""
    rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    emitted_for_current = False

    def flush_current_if_needed() -> None:
        nonlocal emitted_for_current, current
        if current is None or emitted_for_current:
            return
        _append_row(rows, current, pdf_url=pdf_url, scraped_at=scraped_at)
        emitted_for_current = True

    for raw in text.splitlines():
        if not raw.strip() or _SKIP_LINE_RE.search(raw) or _PAGE_FOOTER_RE.match(raw.strip()):
            continue

        primary = _parse_primary_line(raw)
        if primary:
            flush_current_if_needed()
            current = primary
            emitted_for_current = False
            if primary["union_name"] or primary["bargaining_unit_name"]:
                _append_row(rows, primary, pdf_url=pdf_url, scraped_at=scraped_at)
                emitted_for_current = True
            continue

        if current is None:
            continue
        cont = _parse_continuation(raw)
        if not cont:
            continue
        union, unit = cont
        piece = {
            **current,
            "union_name": union,
            "bargaining_unit_name": unit,
        }
        _append_row(rows, piece, pdf_url=pdf_url, scraped_at=scraped_at)
        emitted_for_current = True

    flush_current_if_needed()
    if not rows:
        raise RuntimeError("NV EMRB employer directory PDF parsed 0 rows")
    # Layout PDFs can emit the same employer×union×unit more than once
    # (primary + continuation); keep first occurrence per row_key.
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        key = row["row_key"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    deduped.sort(
        key=lambda row: (
            row["employer_name"].lower(),
            row["union_name"].lower(),
            row["bargaining_unit_name"].lower(),
        )
    )
    return deduped

def _append_row(
    rows: list[dict[str, str]],
    base: dict[str, str],
    *,
    pdf_url: str,
    scraped_at: str,
) -> None:
    employer = base["employer_name"]
    union = base.get("union_name", "")
    unit = base.get("bargaining_unit_name", "")
    row_key = (
        f"{AGENCY_CODE}:{_slug(employer)}:"
        f"{_slug(union) if union else 'NO_UNION'}:"
        f"{_slug(unit) if unit else 'NO_UNIT'}"
    )
    rows.append(
        {
            "row_key": row_key,
            "source_agency_code": AGENCY_CODE,
            "canonical_case_type": "CERTIFICATION",
            "native_case_type": "EMPLOYER_DIRECTORY",
            "employer_name": employer,
            "union_name": union,
            "bargaining_unit_name": unit,
            "contact_name": base.get("contact_name", ""),
            "contact_email": base.get("contact_email", ""),
            "contact_phone": base.get("contact_phone", ""),
            "website": base.get("website", ""),
            "jurisdiction_city": base.get("jurisdiction_city", ""),
            "jurisdiction_state": "NV",
            "employer_street": base.get("employer_street", ""),
            "employer_zip": base.get("employer_zip", ""),
            "source_pdf_url": pdf_url,
            "source_page_url": HOME_URL,
            "source_url": pdf_url,
            "scraped_at": scraped_at,
        }
    )

def scrape_employer_directory(
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
    pdf_url = discover_employer_pdf_url(html)
    pdf_bytes = pdf_fetcher(pdf_url, delay_seconds=delay_seconds)
    text = parse_text(pdf_bytes) if parse_text else _pdf_to_text(pdf_bytes)
    return parse_employer_text(text, pdf_url=pdf_url, scraped_at=scraped_at)

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.25) -> int:
    rows = scrape_employer_directory(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

