"""Rhode Island RISLRB certification tables → employer ACE (GeoCensus) → Redshift (clrr)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.http import fetch_url, fetch_bytes, strip_html_text
from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.pdf import pdf_bytes_to_text

FLOW_NAME = "RISLRB Certifications Flow"
REPORT_PREFIX = "rislrb_certifications"
AGENCY_CODE = "RI_RISLRB"
BASE_URL = "http://rislrb.ri.gov/"

CERTIFICATION_PAGES: tuple[tuple[str, str], ...] = (
    ("Firefighters", "FireFighterCert.htm"),
    ("Police Officers", "PoliceCert.htm"),
    ("Certified Teachers", "TeacherCert.htm"),
    ("Municipal City and Town", "CityTownMuniCert.htm"),
    ("Municipal Non-Professional School", "NonProfMuniCert.htm"),
    ("Municipal Authorities", "AuthorityMuniCert.htm"),
    ("State and Quasi-State", "StateQuasiCert.htm"),
    ("Miscellaneous", "MiscCert.htm"),
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "certification_category",
    "employer_name",
    "union_name",
    "unit_description",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "date_certified",
    "date_amended",
    "certification_pdf_url",
    "disposition_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

# Parentheticals that name a bargaining unit / job class, not a municipality.
_UNIT_PAREN_HINT = re.compile(
    r"(?i)\b("
    r"clerical|custodial|nurse|nurses|housing|management|police|"
    r"crossing|guard|guards|clerk|clerks|aide|aides|driver|drivers|"
    r"secretary|secretaries|rescue|personnel|professional|non-?police|"
    r"fire\s*fighter|teacher|teachers|maintenance|paraprofessional|"
    r"hours?\s+per\s+week|middle\s+management"
    r")\b"
)

# Caption structure is stable; OCR of typescript is not (Flre, chlef, Bul1dlng).
# Match roles loosely: MATTER/MATER, Employer/Emp1oyer, Petitioner/Pet1tioner.
_CAPTION_RE = re.compile(
    r"In\s+the\s+M\w{3,6}\s+of\s+(?P<employer>.+?)\s+"
    r"Emp\w{3,10}\s*-+\s*and\s*-+\s*(?P<union>.+?)\s+"
    r"Pet\w{5,12}",
    flags=re.I | re.S,
)
_UNIT_BALLOT_RE = re.compile(
    r"(?:secret\s+ballot\s+of|by\s+secret\s+ballot\s+of)\s+"
    r"(?P<unit>.+?)(?:\.\s|\.\n|$)",
    flags=re.I | re.S,
)
_CITY_OF_RE = re.compile(
    r"\b(?:City|Town|Village)\s+of\s+(?P<city>[A-Za-z][A-Za-z .'-]{0,40})",
    flags=re.I,
)
_NON_PLACE_EMPLOYER_RE = re.compile(
    r"(?i)\b("
    r"state|quasi|authority|university|college|school\s+department|"
    r"school\s+committee|board\s+of|department\s+of|fire\s+district|"
    r"water\s+district|housing\s+authority|transit|airport"
    r")\b"
)


def _split_employer_unit(employer_name: str) -> tuple[str, str]:
    """Move unit descriptors out of employer_name into unit_description.

    Listing cells often put `(Clerical)` or `(Clerks, Aides, …)` on the employer
    column (infra-36). Keep place parentheticals like `(Lincoln)` / `(Scituate)`
    and amendment notes on the employer string. PDF caption parse fills city and
    can refine employer/union when the listing is thin.
    """
    text = re.sub(r"\s+", " ", employer_name).strip()
    if not text:
        return "", ""

    units: list[str] = []

    def _maybe_peel(match: re.Match[str]) -> str:
        paren = match.group(1).strip()
        lower = paren.lower()
        if lower.startswith("amended"):
            return match.group(0)
        if _UNIT_PAREN_HINT.search(paren) or "," in paren:
            units.append(paren)
            return " "
        return match.group(0)

    cleaned = re.sub(r"\(([^)]+)\)", _maybe_peel, text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;")
    if not cleaned and units:
        return "", "; ".join(units)
    only = re.fullmatch(r"\(([^)]+)\)", text)
    if only and not units:
        # Whole cell was a single parenthetical with no unit hint — leave as-is
        # only when it is clearly a unit-only cell (parens wrapping everything).
        if _UNIT_PAREN_HINT.search(only.group(1)) or "," in only.group(1):
            return "", only.group(1).strip()
    return cleaned, "; ".join(units)

def _normalize_case_number(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())

def _extract_dates(date_cell: str) -> tuple[str, str]:
    primary = ""
    amended = ""
    for match in re.finditer(r"\(?\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*\)?", date_cell):
        token = match.group(1)
        if match.group(0).strip().startswith("("):
            amended = token
        elif not primary:
            primary = token
    if not primary and amended:
        primary = amended
        amended = ""
    return primary, amended


def _clean_caption_party(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" ,;-")
    text = re.sub(r"\s*-\s*and\s*-?\s*$", "", text, flags=re.I).strip(" ,;-")
    return text


def jurisdiction_city_from_employer(employer_name: str) -> str:
    """Return a city only when the employer string explicitly encodes one.

    Do not invent cities for state / quasi-state / district / school employers
    (infra-36 city half). Prefer ``City/Town/Village of X``, then a place
    parenthetical, then a bare municipal name with no non-place tokens.
    """
    text = re.sub(r"\s+", " ", employer_name).strip()
    if not text:
        return ""

    city_of = _CITY_OF_RE.search(text)
    if city_of:
        return city_of.group("city").strip(" ,.")

    place_paren = re.search(r"\(([A-Za-z][A-Za-z .'-]{0,40})\)\s*$", text)
    if place_paren and not _UNIT_PAREN_HINT.search(place_paren.group(1)):
        inner = place_paren.group(1).strip()
        if not _NON_PLACE_EMPLOYER_RE.search(inner):
            return inner

    bare = re.sub(r"\s*\([^)]*\)\s*", " ", text).strip(" ,;")
    if not bare or _NON_PLACE_EMPLOYER_RE.search(bare):
        return ""
    if _UNIT_PAREN_HINT.search(bare):
        return ""
    # Single-token or short municipal names from the listing (Barrington, Bristol).
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{0,40}", bare) and len(bare.split()) <= 3:
        return bare
    return ""


def parse_certification_caption(text: str) -> dict[str, str]:
    """Extract employer, union, unit, and city from certification PDF text.

    Returns empty strings for fields that cannot be recovered. Tolerates OCR
    character errors by matching caption structure rather than exact words.
    """
    flat = re.sub(r"[ \t]+", " ", text)
    flat = re.sub(r"\n+", "\n", flat)
    out = {
        "employer_name": "",
        "union_name": "",
        "unit_description": "",
        "jurisdiction_city": "",
    }
    caption = _CAPTION_RE.search(flat)
    if caption:
        employer = _clean_caption_party(caption.group("employer"))
        union = _clean_caption_party(caption.group("union"))
        out["employer_name"] = employer
        out["union_name"] = union
        out["jurisdiction_city"] = jurisdiction_city_from_employer(employer)

    unit_match = _UNIT_BALLOT_RE.search(flat)
    if unit_match:
        unit = re.sub(r"\s+", " ", unit_match.group("unit")).strip(" .;")
        # Cap runaway matches from a missing period.
        if len(unit) > 400:
            unit = unit[:400].rsplit(" ", 1)[0]
        out["unit_description"] = unit
    return out


def _enrich_row_from_caption(row: dict[str, str], caption: dict[str, str]) -> None:
    """Merge PDF caption fields into a listing row (soft overwrite)."""
    if caption.get("employer_name"):
        # Prefer caption employer when listing was empty or unit-only.
        listing_emp = row.get("employer_name", "").strip()
        if not listing_emp or listing_emp.startswith("("):
            row["employer_name"] = caption["employer_name"]
        elif len(caption["employer_name"]) > len(listing_emp) + 5:
            # Caption usually carries the full municipal form ("City of …").
            row["employer_name"] = caption["employer_name"]
    if caption.get("union_name"):
        listing_union = row.get("union_name", "").strip()
        if not listing_union or len(caption["union_name"]) > len(listing_union) + 5:
            row["union_name"] = caption["union_name"]
    if caption.get("unit_description") and not row.get("unit_description"):
        row["unit_description"] = caption["unit_description"]
    if caption.get("jurisdiction_city"):
        row["jurisdiction_city"] = caption["jurisdiction_city"]
    elif row.get("employer_name"):
        city = jurisdiction_city_from_employer(row["employer_name"])
        if city:
            row["jurisdiction_city"] = city


def _parse_certification_table(
    html: str,
    *,
    category: str,
    page_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    table_match = re.search(
        r'<table[^>]*class="sortable"[^>]*>(.*)',
        html,
        flags=re.I | re.S,
    )
    if not table_match:
        return []

    rows: list[dict[str, str]] = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 5:
            continue
        case_number = strip_html_text(cells[1])
        if not re.match(r"EE-\d+", case_number, flags=re.I):
            continue

        employer_cell = cells[0]
        cert_href = re.search(r'href="([^"]+)"', employer_cell, flags=re.I)
        cert_pdf = urljoin(page_url, cert_href.group(1)) if cert_href else ""
        # Employer text lives inside the <a> (and sometimes after it). Taking only
        # post-</a> text left many cells empty, and the old fallback wrote the raw
        # href="…" attribute into employer_name (infra-36). Never use the href as
        # a display value.
        employer_raw = strip_html_text(employer_cell)
        employer_name, unit_description = _split_employer_unit(employer_raw)

        union_name = strip_html_text(cells[2])
        date_certified, date_amended = _extract_dates(strip_html_text(cells[3]))

        disposition_cell = cells[4]
        disp_href = re.search(r'href="([^"]+)"', disposition_cell, flags=re.I)
        disposition_pdf = urljoin(page_url, disp_href.group(1)) if disp_href else ""

        case_key = _normalize_case_number(case_number)
        canonical = "UNIT_CLARIFICATION" if disposition_pdf else "CERTIFICATION"
        row_key = f"{AGENCY_CODE}:{case_key}:{category}"

        # Listing pages do not state a reliable city. Prefer PDF caption (below);
        # fall back to an explicit municipal form on the employer string only.
        jurisdiction_city = jurisdiction_city_from_employer(employer_name)
        rows.append(
            {
                "row_key": row_key,
                "source_agency_code": AGENCY_CODE,
                "case_number": case_key,
                "canonical_case_type": canonical,
                "native_case_type": "CERTIFICATION",
                "certification_category": category,
                "employer_name": employer_name,
                "union_name": union_name,
                "unit_description": unit_description,
                "jurisdiction_city": jurisdiction_city,
                "jurisdiction_state": "RI",
                "employer_street": "",
                "employer_zip": "",
                "date_certified": date_certified,
                "date_amended": date_amended,
                "certification_pdf_url": cert_pdf,
                "disposition_pdf_url": disposition_pdf,
                "source_page_url": page_url,
                "source_url": cert_pdf or page_url,
                "scraped_at": scraped_at,
            }
        )
    return rows


def enrich_rows_from_certification_pdfs(
    rows: list[dict[str, str]],
    *,
    delay_seconds: float = 0.3,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
) -> list[dict[str, str]]:
    """Fetch each certification PDF and merge caption fields (soft-fail per row)."""
    pdf_fetcher = fetch_pdf or fetch_bytes
    to_text = pdf_to_text or pdf_bytes_to_text
    for row in rows:
        url = row.get("certification_pdf_url") or ""
        if not url:
            if row.get("employer_name") and not row.get("jurisdiction_city"):
                city = jurisdiction_city_from_employer(row["employer_name"])
                if city:
                    row["jurisdiction_city"] = city
            continue
        try:
            pdf_bytes = pdf_fetcher(url, delay_seconds=delay_seconds)
            text = to_text(pdf_bytes)
            caption = parse_certification_caption(text)
            _enrich_row_from_caption(row, caption)
        except Exception:
            # Keep the listing row; one bad PDF must not abort the feed.
            if row.get("employer_name") and not row.get("jurisdiction_city"):
                city = jurisdiction_city_from_employer(row["employer_name"])
                if city:
                    row["jurisdiction_city"] = city
            continue
    return rows


def scrape_certifications(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
    enrich_pdfs: bool = True,
) -> list[dict[str, str]]:
    """Scrape all RISLRB certification category tables, then PDF captions."""
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    all_rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for category, page_name in CERTIFICATION_PAGES:
        page_url = urljoin(BASE_URL, page_name)
        html = fetcher(page_url, delay_seconds=delay_seconds)
        for row in _parse_certification_table(
            html,
            category=category,
            page_url=page_url,
            scraped_at=scraped_at,
        ):
            if row["row_key"] in seen_keys:
                continue
            seen_keys.add(row["row_key"])
            all_rows.append(row)

    if enrich_pdfs:
        enrich_rows_from_certification_pdfs(
            all_rows,
            delay_seconds=delay_seconds,
            fetch_pdf=fetch_pdf,
            pdf_to_text=pdf_to_text,
        )

    all_rows.sort(key=lambda row: (row["case_number"], row["certification_category"]))
    return all_rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    rows = scrape_certifications(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)
