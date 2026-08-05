"""Illinois ILRB bargaining-unit certification FY PDFs.

WHAT THIS FILE IS FOR
---------------------
ILRB publishes fiscal-year “Elections certified” PDF lists under
https://ilrb.illinois.gov/decisions/bargainingcertifications.html (FY07–present).
Each PDF is a multi-column Case No / Employer / Labor Organization table
(State Panel `S-*` and Local Panel `L-*`).

This flow discovers every FY PDF on the hub, parses one wide row per case
(merged companion `and` case numbers), then hands rows to shared state-PERB
ACE (GeoCensus) on employer + IL jurisdiction.

IELRB (education) is out of scope — separate board/site.
pdftotext (poppler) is required.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url, fetch_bytes
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "IL ILRB Bargaining Certifications Flow"
REPORT_PREFIX = "il_ilrb_bargaining_certs"
AGENCY_CODE = "IL_ILRB"
BASE_URL = "https://ilrb.illinois.gov"
LISTING_URL = f"{BASE_URL}/decisions/bargainingcertifications.html"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "panel",
    "fiscal_year",
    "canonical_case_type",
    "native_case_type",
    "certified_date",
    "employer_name",
    "union_name",
    "prevailing_party",
    "employees",
    "bargaining_unit_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_pdf_url",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_PDF_ANCHOR_RE = re.compile(
    r"""<a[^>]+href=["']([^"']+\.pdf[^"']*)["'][^>]*>(.*?)</a>""",
    flags=re.I | re.S,
)
_CASE_LINE_RE = re.compile(r"^\s*([SL]-[A-Z]{1,4}-\d{2}-\d{3})\b")
_CASE_RE = re.compile(r"([SL]-[A-Z]{1,4}-\d{2}-\d{3})")
_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/(?:\d{2}|\d{4}))\b")
_FY_FROM_HREF_RE = re.compile(r"fy\s*[-_]?(\d{2})", flags=re.I)
_FY_FROM_RANGE_RE = re.compile(
    r"July\s+1,\s*(?P<y1>20\d{2})\s*[-–—]\s*June\s+30,\s*(?P<y2>20\d{2})",
    flags=re.I,
)
_LABEL_STRIP = re.compile(
    r"\b(Majority\s+Interest|Amended\s+Certification|Amended\s+Certificat|"
    r"Interest|Majority|Election|Certification)\b",
    flags=re.I,
)
_SKIP_LINE = re.compile(
    r"CERTIFICATIONS OF|BARGAINING UNITS CERTIFIED|ILLINOIS LABOR RELATIONS|"
    r"July 1,\s*\d{4}|Labor\s+Organization|Unit Description|"
    r"^\s*Date\s+Prevailing|^\s*Case\s+Number\b",
    flags=re.I,
)

def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)

def _clean(value: str) -> str:
    text = (
        value.replace("\xa0", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
    )
    text = _LABEL_STRIP.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" ,;")

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
                "pdftotext is required to parse IL ILRB certification PDFs"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftotext failed: {exc.stderr or exc.stdout or exc}"
            ) from exc
        return completed.stdout

def _strip_tags(html: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", html))

def fiscal_year_from_pdf_ref(href: str, label: str) -> str:
    """Return FY label like FY26 from href/label text."""
    range_match = _FY_FROM_RANGE_RE.search(label) or _FY_FROM_RANGE_RE.search(
        unquote(href)
    )
    if range_match:
        return f"FY{int(range_match.group('y2')) % 100:02d}"
    fy_match = _FY_FROM_HREF_RE.search(unquote(href)) or _FY_FROM_HREF_RE.search(
        label
    )
    if fy_match:
        return f"FY{int(fy_match.group(1)):02d}"
    raise RuntimeError(f"Cannot infer fiscal year from PDF href={href!r} label={label!r}")

def list_fy_pdfs(html: str) -> list[tuple[str, str, str]]:
    """Return unique [(fiscal_year, pdf_url, label), ...] newest FY first."""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for href, raw_label in _PDF_ANCHOR_RE.findall(html):
        if "certif" not in href.lower() and "certif" not in raw_label.lower():
            # Hub only links cert PDFs, but keep a soft filter
            if "fy" not in href.lower():
                continue
        url = _absolute_url(href)
        key = unquote(url).lower()
        if key in seen:
            continue
        label = _strip_tags(raw_label) or unquote(url.rsplit("/", 1)[-1])
        try:
            fy = fiscal_year_from_pdf_ref(href, label)
        except RuntimeError:
            continue
        seen.add(key)
        found.append((fy, url, label))
    found.sort(key=lambda item: item[0], reverse=True)
    return found

def _cell(line: str, start: int, end: int | None) -> str:
    if len(line) <= start:
        return ""
    return line[start:] if end is None else line[start:end]

def _heal(left: str, right: str) -> tuple[str, str]:
    """Move a flush-right fragment into right when a column boundary splits a word."""
    if not left or not right or left.endswith((" ", "\t")):
        return left, right
    match = re.search(r"^(.*?)(\S+)$", left.rstrip())
    if not match:
        return left, right
    prefix, frag = match.group(1), match.group(2)
    right_stripped = right.lstrip()
    if not right_stripped:
        return left, right
    first = right_stripped[0]
    looks_split = (
        first.islower()
        or first == "'"
        or (frag.isdigit() and first.isdigit())
        or (len(frag) <= 2 and frag.isalpha() and first.isalpha())
    )
    if not looks_split:
        return left, right
    pad = len(left) - len(left.rstrip())
    return prefix + (" " * pad), frag + right_stripped

def detect_column_bounds(lines: list[str]) -> tuple[int, ...]:
    """Return (case0, case_end, labor_start, cert, party, emps, emps_end, unit)."""
    header = ""
    for line in lines[:12]:
        if re.search(r"Case\s+(?:No\.?|Number)\b", line, re.I) and re.search(
            r"Employer", line, re.I
        ):
            header = line
            break
    if not header:
        return (0, 12, 36, 65, 77, 94, 110, 110)

    emp = header.find("Employer")
    labor = header.find("Labor")
    if labor < 0:
        labor = header.find("Organization")
    cert = header.find("Certified")
    party = header.find("Party")
    if party < 0:
        party = header.find("Prevailing")
    emps = header.find("Employees")
    if emps < 0:
        emps = header.find("No. of")
    unit = header.find("Unit")

    case_end = 20 if emp >= 24 else 12
    labor_start = labor if labor > 0 else max(emp + 15, 38)
    if emp <= 20 and labor >= 38:
        labor_start = 36  # FY26 vintage bleeds one glyph left of Labor header
    cert_start = cert if cert > 0 else labor_start + 25
    party_start = party if party > cert_start else cert_start + 12
    emps_start = emps if emps > party_start else party_start + 16
    if unit > emps_start:
        emps_end = min(unit, emps_start + 16)
        unit_start = unit
    else:
        emps_end = emps_start + 16
        unit_start = emps_end
    return (
        0,
        case_end,
        labor_start,
        cert_start,
        party_start,
        emps_start,
        emps_end,
        unit_start,
    )

def _split_blocks(lines: list[str]) -> list[tuple[list[str], list[str]]]:
    idxs = [
        i
        for i, line in enumerate(lines)
        if _CASE_LINE_RE.match(line.replace("\x0c", ""))
    ]
    blocks: list[tuple[list[str], list[str]]] = []
    i = 0
    while i < len(idxs):
        start = idxs[i]
        cases = [
            _CASE_LINE_RE.match(lines[start].replace("\x0c", "")).group(1)  # type: ignore[union-attr]
        ]
        j = i + 1
        while j < len(idxs):
            between = lines[idxs[j - 1] + 1 : idxs[j]]
            if between and all(
                re.fullmatch(r"\s*|and", ln.replace("\x0c", "").strip(), flags=re.I)
                for ln in between
            ):
                cases.append(
                    _CASE_LINE_RE.match(lines[idxs[j]].replace("\x0c", "")).group(1)  # type: ignore[union-attr]
                )
                j += 1
                continue
            break
        end = idxs[j] if j < len(idxs) else len(lines)
        blocks.append((cases, lines[start:end]))
        i = j
    return blocks

def _normalize_date(raw: str) -> str:
    parts = raw.split("/")
    if len(parts) != 3:
        return raw
    if len(parts[2]) == 2:
        year = int(parts[2])
        parts[2] = str(2000 + year if year < 80 else 1900 + year)
    return "/".join(parts)

def _jurisdiction_city(employer_name: str) -> str:
    match = re.search(r"^([^,]+),\s*(City|Village|Town)\s+of\b", employer_name, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"(City|Village|Town|County)\s+of\s+([^,(]+)", employer_name, re.I)
    if match:
        return match.group(2).strip()
    if re.search(r"\bCounty\b", employer_name, re.I):
        return employer_name.split(",")[0].strip()
    if employer_name.lower().startswith("state of"):
        return ""
    return employer_name.split(",")[0].split("(")[0].strip()[:80]

def parse_certs_text(
    text: str,
    *,
    fiscal_year: str,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    """Parse pdftotext -layout output for one FY certifications PDF."""
    lines = text.splitlines()
    bounds = detect_column_bounds(lines)
    (
        _c0,
        case_end,
        labor_start,
        cert_start,
        party_start,
        emps_start,
        emps_end,
        unit_start,
    ) = bounds

    rows: list[dict[str, str]] = []
    for cases, block_lines in _split_blocks(lines):
        emp_parts: list[str] = []
        labor_parts: list[str] = []
        party_parts: list[str] = []
        unit_parts: list[str] = []
        case_bits: list[str] = []
        certified = ""
        date_line_employees = ""

        for raw in block_lines:
            line = raw.replace("\x0c", "")
            if _SKIP_LINE.search(line) and not _CASE_LINE_RE.match(line):
                continue
            if re.search(r"Case\s+(?:No\.?|Number)\b", line, re.I) and "Employer" in line:
                continue

            case_c = _cell(line, 0, case_end)
            emp_c = _cell(line, case_end, labor_start)
            lab_c = _cell(line, labor_start, cert_start)
            cert_c = _cell(line, cert_start, party_start)
            party_c = _cell(line, party_start, emps_start)
            emps_c = _cell(line, emps_start, emps_end)
            unit_c = _cell(line, unit_start, None)

            case_c, emp_c = _heal(case_c, emp_c)
            emp_c, lab_c = _heal(emp_c, lab_c)
            lab_c, cert_c = _heal(lab_c, cert_c)
            emps_c, unit_c = _heal(emps_c, unit_c)

            bit = _CASE_RE.sub("", case_c)
            bit = _LABEL_STRIP.sub(" ", bit)
            bit = re.sub(r"^\s*and\s*$", "", bit, flags=re.I)
            if bit.strip():
                case_bits.append(bit)
            if emp_c.strip():
                emp_parts.append(emp_c)
            if lab_c.strip():
                labor_parts.append(lab_c)
            if party_c.strip():
                party_parts.append(party_c)
            if unit_c.strip():
                unit_parts.append(unit_c)

            date_match = _DATE_RE.search(cert_c) or _DATE_RE.search(cert_c + party_c)
            if date_match and not certified:
                certified = _normalize_date(date_match.group(1))
                date_line_employees = emps_c
                if party_c.strip():
                    party_parts = [party_c] + [p for p in party_parts if p != party_c]

        employer = _clean(" ".join(case_bits + emp_parts))
        union = _clean(" ".join(labor_parts))
        if re.fullmatch(r"\d{1,4}", union or ""):
            # Spill from a prior Local-NNNN line — drop numeric-only garbage
            union = ""
        party = _clean(" ".join(party_parts))
        unit = _clean(" ".join(unit_parts))

        employees = ""
        emp_src = date_line_employees
        emp_match = re.search(r"(?<!\d)(\d{1,4})(?!\d)", emp_src or "")
        if emp_match:
            employees = emp_match.group(1)

        head = " ".join(block_lines[:6])
        if re.search(r"Majority\s+Interest", head, re.I) or (
            re.search(r"\bMajority\b", head, re.I) and re.search(r"\bInterest\b", head, re.I)
        ):
            native = "MAJORITY_INTEREST"
        elif re.search(r"Amended", head, re.I):
            native = "AMENDED_CERTIFICATION"
        elif re.search(r"\bElection\b", head, re.I):
            native = "ELECTION"
        else:
            native = cases[0].split("-")[1]

        code = cases[0].split("-")[1]
        if code in ("DD", "DC"):
            canonical = "DECERTIFICATION"
        elif code == "UC":
            canonical = "UNIT_CLARIFICATION"
        else:
            canonical = "CERTIFICATION"

        case_number = "+".join(cases)
        rows.append(
            {
                "row_key": f"{AGENCY_CODE}:{fiscal_year}:{case_number}",
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "panel": "Local" if cases[0].startswith("L-") else "State",
                "fiscal_year": fiscal_year,
                "canonical_case_type": canonical,
                "native_case_type": native,
                "certified_date": certified,
                "employer_name": employer[:220],
                "union_name": union[:220],
                "prevailing_party": party[:80],
                "employees": employees,
                "bargaining_unit_name": unit[:500],
                "jurisdiction_city": _jurisdiction_city(employer)[:80],
                "jurisdiction_state": "IL",
                "employer_street": "",
                "employer_zip": "",
                "source_pdf_url": pdf_url,
                "source_page_url": LISTING_URL,
                "source_url": pdf_url,
                "scraped_at": scraped_at,
            }
        )
    return rows

def scrape_bargaining_certs(
    *,
    delay_seconds: float = 0.35,
    fetch_html: Any = None,
    fetch_pdf: Any = None,
    parse_text: Any = None,
) -> list[dict[str, str]]:
    html_fetcher = fetch_html or fetch_url
    pdf_fetcher = fetch_pdf or fetch_bytes
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    html = html_fetcher(LISTING_URL, delay_seconds=delay_seconds)
    pdfs = list_fy_pdfs(html)
    if not pdfs:
        raise RuntimeError(f"No FY certification PDFs found on {LISTING_URL}")

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for fiscal_year, pdf_url, _label in pdfs:
        pdf_bytes = pdf_fetcher(pdf_url, delay_seconds=delay_seconds)
        text = parse_text(pdf_bytes) if parse_text else _pdf_to_text(pdf_bytes)
        for row in parse_certs_text(
            text,
            fiscal_year=fiscal_year,
            pdf_url=pdf_url,
            scraped_at=scraped_at,
        ):
            if row["row_key"] in seen_keys:
                continue
            seen_keys.add(row["row_key"])
            rows.append(row)

    if not rows:
        raise RuntimeError("IL ILRB certification scrape parsed 0 rows")
    rows.sort(key=lambda row: (row["fiscal_year"], row["case_number"]), reverse=True)
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.35) -> int:
    rows = scrape_bargaining_certs(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

