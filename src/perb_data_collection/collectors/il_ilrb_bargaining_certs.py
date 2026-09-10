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
    "table_heading",
    "canonical_case_type",
    "native_case_type",
    "certified_date",
    "employer_name",
    "agency",
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
    r"CERTIFICATION OF VOLUNTARILY|AMENDMENT TO CERTIFICATIONS|"
    r"REVOCATION OF PRIOR|July 1,\s*\d{4}|Labor\s+Organization|Unit Description|"
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

# ---------------------------------------------------------------------------
# Header-driven table mapping
#
# Each FY volume holds several tables (certifications of representative,
# voluntary recognition, amendment of certification, gubernatorial designation
# S-DE, unit clarification, revocation of prior certification). They do not
# share a column layout: the S-DE table has no Labor Organization column at
# all and carries a State Agency column instead. Column bounds are therefore
# computed per table from that table's own header row, and cells are mapped by
# header label rather than by position.
# ---------------------------------------------------------------------------

_HEADER_LINE_RE = re.compile(r"Case\s+(?:No\.?|Number)\b", re.I)
_DATE_RANGE_RE = re.compile(r"July\s+1,\s*\d{4}", re.I)
_HEADER_WORDS = {
    "date",
    "prevailing",
    "party",
    "no",
    "no.",
    "of",
    "#",
    "u",
    "unit",
    "state",
    "agency",
    "employees",
    "positions",
    "case",
    "name",
    "number",
    "employer",
    "labor",
    "organization",
    "certified",
    "description",
    "type",
    "amendment",
    "revocation",
    "certification",
    "unit4/",
}


def _token_groups(line: str) -> list[tuple[int, int, str]]:
    """Group header tokens separated by a single space into one label."""
    tokens = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", line)]
    groups: list[tuple[int, int, str]] = []
    for start, end, text in tokens:
        # "Employees" and "Positions" are always their own column head. FY25
        # prints "Prevailing Party Employees" with a single space, which would
        # otherwise glue the party and headcount columns into one label.
        starts_column = text.strip(",.").lower() in ("employees", "positions")
        if groups and not starts_column and start - groups[-1][1] <= 1:
            prev = groups[-1]
            groups[-1] = (prev[0], end, f"{prev[2]} {text}")
        else:
            groups.append((start, end, text))
    return groups


def _role_for(label: str) -> str:
    """Map a (prefix + header) label to a wide-row role."""
    low = label.lower()
    if "case" in low:
        return "case"
    if "employer" in low:
        return "employer"
    if "labor" in low or "organization" in low:
        return "union"
    if "agency" in low:
        return "agency"
    if "unit" in low or "amendment" in low or low.startswith("u "):
        return "unit"
    if "employees" in low or "positions" in low:
        return "employees"
    # "Certified", "Date Certified", "Certification Date", "Date Revocation".
    if "certif" in low or "revocation" in low or "date" in low:
        return "certified"
    if "party" in low or "prevailing" in low:
        return "party"
    return "unit"


def _columns_from_header(header: str, prefix_line: str) -> list[tuple[str, int]]:
    """Return [(role, nominal_start), ...] in left-to-right order."""
    groups = _token_groups(header)
    prefixes = _token_groups(prefix_line) if prefix_line else []
    columns: list[tuple[str, int]] = []
    seen: dict[str, int] = {}
    for start, end, label in groups:
        prefix = ""
        for p_start, p_end, p_label in prefixes:
            if p_start < end + 4 and start - 4 < p_end:
                prefix = p_label
                break
        role = _role_for(f"{prefix} {label}".strip())
        seen[role] = seen.get(role, 0) + 1
        if seen[role] > 1:
            role = f"{role}#{seen[role]}"
        columns.append((role, start))
    return columns


def _base_role(role: str) -> str:
    return role.split("#", 1)[0]


def _clean_heading(value: str) -> str:
    """Normalise a banner without _LABEL_STRIP, which eats "CERTIFICATION"."""
    text = value.replace("\xa0", " ").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip(" ,;")


def _is_banner(line: str) -> bool:
    text = line.strip()
    if len(text) < 10 or _CASE_RE.search(text) or _DATE_RANGE_RE.search(text):
        return False
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _is_header_ish(line: str) -> bool:
    tokens = line.split()
    if not tokens:
        return False
    return all(tok.strip(",.").lower() in _HEADER_WORDS for tok in tokens)


def _section_heading(lines: list[str], header_i: int) -> str:
    banners: list[str] = []
    for i in range(header_i - 1, max(-1, header_i - 9), -1):
        line = lines[i]
        if _is_banner(line):
            banners.insert(0, line.strip())
            continue
        stripped = line.strip()
        if (
            not stripped
            or _DATE_RANGE_RE.search(line)
            or _is_header_ish(line)
            or re.fullmatch(r"(?i)FY\s*\d{2,4}", stripped)
        ):
            continue
        break
    if not banners:
        for i in range(header_i + 1, min(len(lines), header_i + 9)):
            line = lines[i]
            if _CASE_LINE_RE.match(line):
                break
            if _is_banner(line):
                banners.append(line.strip())
                break
    return _clean_heading(" ".join(banners))


def find_table_sections(
    lines: list[str],
) -> list[tuple[str, int, list[tuple[str, int]]]]:
    """Return [(heading, header_line_number, columns), ...] for one FY volume."""
    sections: list[tuple[str, int, list[tuple[str, int]]]] = []
    for i, line in enumerate(lines):
        if not (_HEADER_LINE_RE.search(line) and re.search(r"Employer", line, re.I)):
            continue
        prefix_line = ""
        for j in range(i - 1, max(-1, i - 4), -1):
            if lines[j].strip() and _is_header_ish(lines[j]):
                prefix_line = lines[j]
                break
        columns = _columns_from_header(line, prefix_line)
        sections.append((_section_heading(lines, i), i, columns))
    return sections


def _bounds_from_gaps(line: str, starts: list[int]) -> list[int] | None:
    """Boundaries taken from this line's own gaps, when every column is present.

    Two shapes are tried: the whole row read off its runs of two or more
    spaces, and — when the line opens with a case number that is followed by a
    single space — the case number as the first boundary and the remaining
    gaps for the rest.
    """
    body = line.rstrip()
    wanted = len(starts) - 1
    if wanted <= 0:
        return None
    attempts: list[tuple[int, list[tuple[int, int]]]] = []
    case_match = _CASE_LINE_RE.match(body)
    if case_match:
        after = case_match.end()
        attempts.append(
            (
                after,
                [
                    (m.start(), m.end())
                    for m in re.finditer(r"\s{2,}", body)
                    if m.start() >= after
                ],
            )
        )
    attempts.append(
        (
            None,  # type: ignore[arg-type]
            [
                (m.start(), m.end())
                for m in re.finditer(r"\s{2,}", body)
                if m.start() > 0
            ],
        )
    )
    for anchor, gaps in attempts:
        first = [] if anchor is None else [anchor]
        if len(gaps) != wanted - len(first):
            continue
        bounds = [0, *first]
        nominals = starts[1 + len(first) :]
        ok = True
        for nominal, (g0, g1) in zip(nominals, gaps, strict=True):
            snapped = min(max(nominal, g0), g1)
            if abs(snapped - nominal) > 30:
                ok = False
                break
            bounds.append(max(snapped, bounds[-1]))
        if ok and len(bounds) == len(starts):
            return bounds
    return None


def _effective_bounds(line: str, starts: list[int]) -> list[int]:
    """Return this line's column boundaries, snapped onto its whitespace gaps.

    Header rows appear once per table but a table runs over many pages, and the
    later pages drift a few glyphs. So the nominal header positions are only a
    hint: the boundaries actually used are the line's own runs of two or more
    spaces.
    """
    exact = _bounds_from_gaps(line, starts)
    if exact is not None:
        return _anchor_case_bound(line, exact)

    body = line.rstrip()
    all_gaps = [(m.start(), m.end()) for m in re.finditer(r"\s{2,}", body)]
    all_gaps.append((len(body), len(body) + 4096))
    bounds = [0]
    for nominal in starts[1:]:
        best = nominal
        if not any(g0 <= nominal <= g1 for g0, g1 in all_gaps):
            distance = None
            for g0, g1 in all_gaps:
                if nominal > g1:
                    dist, cand = nominal - g1, g1
                else:
                    dist, cand = g0 - nominal, g0
                if distance is None or dist < distance:
                    distance, best = dist, cand
            if distance is not None and distance > 18:
                best = nominal
        bounds.append(max(best, bounds[-1]))
    return _anchor_case_bound(line, bounds)


def _anchor_case_bound(line: str, bounds: list[int]) -> list[int]:
    """The case column holds exactly the case number, or nothing at all.

    A wrapped employer name often starts left of the Employer header, and
    without this it would be read as case-column text and then reordered ahead
    of the rest of the name.
    """
    if len(bounds) < 2:
        return bounds
    case_match = _CASE_LINE_RE.match(line)
    bounds[1] = case_match.end() if case_match else 0
    for k in range(2, len(bounds)):
        bounds[k] = max(bounds[k], bounds[k - 1])
    return bounds


def _heal_split_word(left: str, right: str) -> tuple[str, str]:
    """Move a flush-right fragment rightwards when a boundary splits a word.

    Header driven bounds put the boundary in a gap whenever the line shows one,
    but some rows separate two columns by a single space (FY25 prints
    "Hazel Crest Park District International Union"), and there the boundary
    can still land inside a word.
    """
    if not left or not right or left.endswith((" ", "\t")) or right[0].isspace():
        # A split word has whitespace on neither side of the boundary.
        return left, right
    match = re.search(r"^(.*?)(\S+)$", left.rstrip())
    if not match:
        return left, right
    prefix, frag = match.group(1), match.group(2)
    tail = right.lstrip()
    if not tail:
        return left, right
    first = tail[0]
    looks_split = (
        first.islower()
        or first in "'\u2019\u2018"
        or (frag.isdigit() and first.isdigit())
    )
    if not looks_split:
        return left, right
    pad = len(left) - len(left.rstrip())
    return prefix + (" " * pad), frag + tail


def _row_cells(line: str, columns: list[tuple[str, int]]) -> list[tuple[str, str]]:
    starts = [start for _role, start in columns]
    bounds = _effective_bounds(line, starts)
    cells: list[tuple[str, str]] = []
    for idx, (role, _start) in enumerate(columns):
        begin = bounds[idx]
        end = bounds[idx + 1] if idx + 1 < len(bounds) else None
        cells.append((role, line[begin:] if end is None else line[begin:end]))
    for idx in range(len(cells) - 1):
        left, right = _heal_split_word(cells[idx][1], cells[idx + 1][1])
        cells[idx] = (cells[idx][0], left)
        cells[idx + 1] = (cells[idx + 1][0], right)
    return cells


def _calibrated_starts(
    block_lines: list[str], columns: list[tuple[str, int]]
) -> list[int]:
    """Re-anchor the column starts on this row's own fully populated line.

    A table's header prints once but the table runs over many pages, and the
    later pages drift a few glyphs left or right. The line that carries the
    date is the one line of a row with every column filled, so its gaps give
    the true column starts for that row.
    """
    starts = [start for _role, start in columns]
    cert_idx = next(
        (i for i, (role, _s) in enumerate(columns) if _base_role(role) == "certified"),
        None,
    )
    for line in block_lines:
        candidate = _bounds_from_gaps(line, starts)
        if candidate is None:
            continue
        if cert_idx is not None:
            stop = (
                candidate[cert_idx + 1]
                if cert_idx + 1 < len(candidate)
                else len(line)
            )
            if not _DATE_RE.search(line[candidate[cert_idx] : stop]):
                continue
        return candidate
    return starts


def _split_blocks(
    lines: list[str], columns: list[tuple[str, int]]
) -> list[tuple[list[str], list[str]]]:
    idxs = [i for i, line in enumerate(lines) if _CASE_LINE_RE.match(line)]

    def _is_bare_case_line(index: int) -> bool:
        """A stacked companion: a case number with no employer and no date."""
        cells = dict(_row_cells(lines[index], columns))
        if (cells.get("employer") or "").strip():
            return False
        for role, _start in columns:
            if _base_role(role) == "certified" and _DATE_RE.search(
                cells.get(role, "")
            ):
                return False
        return True

    blocks: list[tuple[list[str], list[str]]] = []
    i = 0
    while i < len(idxs):
        case_line = idxs[i]
        cases = [
            _CASE_LINE_RE.match(lines[case_line]).group(1)  # type: ignore[union-attr]
        ]
        j = i + 1
        while j < len(idxs):
            between = [lines[k].strip() for k in range(idxs[j - 1] + 1, idxs[j])]
            if not all(re.fullmatch(r"|and", ln, flags=re.I) for ln in between):
                break
            # Companion cases are either stacked with a literal "and" between
            # them, or listed as bare case numbers under one designation. A
            # blank line alone separates two independent rows.
            joined = any(re.fullmatch(r"and", ln, flags=re.I) for ln in between)
            if not joined and not _is_bare_case_line(idxs[j]):
                break
            cases.append(
                _CASE_LINE_RE.match(lines[idxs[j]]).group(1)  # type: ignore[union-attr]
            )
            j += 1
        end = idxs[j] if j < len(idxs) else len(lines)
        start = 0 if i == 0 else case_line
        blocks.append((cases, lines[start:end]))
        i = j
    return blocks


def _is_centered_layout(lines: list[str], columns: list[tuple[str, int]]) -> bool:
    """True when wrapped cells sit ABOVE their case line (FY26+ vertical centring).

    In the older volumes rows are top aligned and every wrapped line sits below
    its case number, so nothing needs carrying to the next row.
    """
    case_idxs = [i for i, ln in enumerate(lines) if _CASE_LINE_RE.match(ln)]
    if not case_idxs:
        return False
    hits = 0
    for i in case_idxs:
        if i == 0:
            continue
        prev = lines[i - 1]
        if not prev.strip() or _CASE_LINE_RE.match(prev):
            continue
        cells = dict(_row_cells(prev, columns))
        if (cells.get("employer") or "").strip() or (cells.get("union") or "").strip():
            hits += 1
    return hits > len(case_idxs) * 0.3


def _labor_name_incomplete(parts: list[str]) -> bool:
    """True when wrapped labor still expects another line (ends in of/and/Int'l/…)."""
    text = _clean(" ".join(parts))
    if not text:
        return True
    # Explicitly complete: local/lodge number or "… Labor Council" / "Council 31".
    if re.search(
        r"(?i)(?:\b(?:Local|Lodge|Chapter)\s*#?\s*\d+\s*$|"
        r"Labor Council\s*$|"
        r"\bCouncil\s+\d+\s*$)",
        text,
    ):
        return False
    return bool(
        re.search(
            r"(?i)\b("
            r"of|and|the|Int['’]?l|International|Association|Federation|"
            r"Brotherhood|Alliance|Order|Employees|Union,"
            r")\s*$",
            text,
        )
    )


def _strip_neighbor_bleed(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove next-case employer/union text glued onto the current row (infra-38)."""
    for i in range(len(rows) - 1):
        for field in ("employer_name", "union_name"):
            cur = rows[i].get(field) or ""
            nxt = rows[i + 1].get(field) or ""
            if len(nxt) < 12 or not cur:
                continue
            idx = cur.find(nxt)
            if idx > 0 and (cur[idx - 1].isspace() or cur[idx - 1] in ",;"):
                rows[i][field] = cur[:idx].rstrip(" ,;")
                continue
            words = nxt.split()
            if len(words) < 3:
                continue
            for take in range(len(words), 2, -1):
                prefix = " ".join(words[:take])
                if len(prefix) < 20:
                    break
                idx = cur.find(prefix)
                if idx > 0 and (cur[idx - 1].isspace() or cur[idx - 1] in ",;"):
                    rows[i][field] = cur[:idx].rstrip(" ,;")
                    break
        rows[i]["jurisdiction_city"] = _jurisdiction_city(
            rows[i].get("employer_name") or ""
        )[:80]
    return rows

def _normalize_date(raw: str) -> str:
    parts = raw.split("/")
    if len(parts) != 3:
        return raw
    if len(parts[2]) == 2:
        year = int(parts[2])
        parts[2] = str(2000 + year if year < 80 else 1900 + year)
    return "/".join(parts)

def _jurisdiction_city(employer_name: str) -> str:
    if not employer_name or re.search(
        r"(?i)Declaration of Disinterest|\bPolice\s*#|\bOrder of Labor",
        employer_name,
    ):
        return ""
    match = re.search(r"^([^,]+),\s*(City|Village|Town)\s+of\b", employer_name, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"(City|Village|Town|County)\s+of\s+([^,(]+)", employer_name, re.I)
    if match:
        city = match.group(2).strip()
        city = re.sub(r"\s+Local\b.*$", "", city, flags=re.I).strip()
        return city
    if re.search(r"\bCounty\b", employer_name, re.I):
        return employer_name.split(",")[0].strip()
    if employer_name.lower().startswith("state of"):
        return ""
    city = employer_name.split(",")[0].split("(")[0].strip()[:80]
    if re.search(r"(?i)\b(Local|Association|Union|Council)\b", city):
        return ""
    return city


def _heal_shredded_fields(
    *,
    certified: str,
    employer: str,
    union: str,
    party: str,
) -> tuple[str, str, str, str]:
    """Recover a date that still landed in union/party, and drop a digit-only party.

    Header driven bounds keep the Date Certified glyph in its own column, so on
    current volumes this is a no-op. It stays as a backstop for a page whose
    header row failed to render.
    """
    haystack = f"{union} {party} {employer}"
    if not certified:
        full = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", haystack)
        short = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2})\b", haystack)
        truncated = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,3})\b", haystack)
        slash_year = re.search(r"(?<!\d)(/?\d{1,2}/\d{4})\b", haystack)
        pick = full or short or truncated or slash_year
        if pick:
            raw = pick.group(1).lstrip("/")
            parts = raw.split("/")
            if len(parts) == 3 and len(parts[2]) == 3:
                # Incomplete year — do not invent the missing digit
                pass
            else:
                certified = _normalize_date(raw)

    if certified:
        union = _DATE_RE.sub(" ", union)
        union = re.sub(r"(?<!\d)/\d{4}\b", " ", union)
        union = re.sub(r"(?<=\s)\d{1,2}/(?=\s|$|[A-Za-z])", " ", union)
        union = re.sub(r"\s+", " ", union).strip(" ,/")
    else:
        if re.search(r"(?<=\s)\d{1,2}/(?=\s|$|[A-Za-z])", union or ""):
            union = re.sub(r"(?<=\s)\d{1,2}/(?=\s|$|[A-Za-z])", " ", union)
            union = re.sub(r"\s+", " ", union).strip(" ,/")

    if party and (
        re.fullmatch(r"\d{1,4}", party)
        or (len(party) <= 24 and not re.search(r"(?i)[A-Za-z]{3,}", party))
        or re.fullmatch(r"[\d\s/]+", party)
    ):
        party = ""

    return certified, employer, union, party


def _parse_section(
    section_lines: list[str],
    columns: list[tuple[str, int]],
    heading: str,
    *,
    fiscal_year: str,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    roles = [role for role, _start in columns]
    has_union = any(_base_role(role) == "union" for role in roles)
    centered = _is_centered_layout(section_lines, columns)

    rows: list[dict[str, str]] = []
    carry: dict[str, list[str]] = {}

    for cases, block_lines in _split_blocks(section_lines, columns):
        local_columns = [
            (role, start)
            for (role, _nominal), start in zip(
                columns, _calibrated_starts(block_lines, columns), strict=True
            )
        ]
        parts: dict[str, list[str]] = {
            role: list(carry.get(role, [])) for role in set(roles)
        }
        carry = {}
        certified = ""
        date_line_employees = ""

        for raw in block_lines:
            line = raw.replace("\x0c", "")
            if _HEADER_LINE_RE.search(line) and re.search(r"Employer", line, re.I):
                continue
            if _SKIP_LINE.search(line) and not _CASE_LINE_RE.match(line):
                continue
            if _is_banner(line) or (
                _is_header_ish(line) and not _CASE_LINE_RE.match(line)
            ):
                continue

            cells = dict(_row_cells(line, local_columns))

            def _case_bit(cell: str) -> str:
                bit = _CASE_RE.sub("", cell)
                bit = _LABEL_STRIP.sub(" ", bit)
                return re.sub(r"^\s*and\s*$", "", bit, flags=re.I)

            cert_cell = cells.get("certified", "")
            date_match = _DATE_RE.search(cert_cell)

            if certified and centered and has_union:
                # FY26+ pages centre a row vertically, so once the date line is
                # past, employer/union/party text belongs to the NEXT case.
                union_so_far: list[str] = []
                for role in roles:
                    if _base_role(role) == "union":
                        union_so_far.extend(parts.get(role, []))
                if _labor_name_incomplete(union_so_far):
                    pass  # keep collecting the wrapped labor name below
                else:
                    moved = False
                    for role in roles:
                        if _base_role(role) not in (
                            "case",
                            "employer",
                            "union",
                            "party",
                            "agency",
                        ):
                            continue
                        cell = cells.get(role, "")
                        if not cell.strip():
                            continue
                        text = _case_bit(cell) if _base_role(role) == "case" else cell
                        if not text.strip():
                            continue
                        carry.setdefault(role, []).append(text)
                        moved = True
                    if moved:
                        continue

            for role, cell in cells.items():
                base = _base_role(role)
                if base in ("certified", "employees"):
                    continue
                if not cell.strip():
                    continue
                if base == "case":
                    continue
                if base == "employer":
                    cell = _case_bit(cell)
                    if not cell.strip():
                        continue
                if base == "party" and cell.strip().isdigit():
                    continue
                parts.setdefault(role, []).append(cell)

            if date_match and not certified:
                certified = _normalize_date(date_match.group(1))
                date_line_employees = " ".join(
                    cells.get(role, "")
                    for role in roles
                    if _base_role(role) == "employees"
                )

        def _joined(base: str) -> str:
            chunks: list[str] = []
            for role in roles:
                if _base_role(role) == base:
                    chunks.extend(parts.get(role, []))
            return _clean(" ".join(chunks))

        employer = _joined("employer")
        union = _joined("union") if has_union else ""
        if re.fullmatch(r"\d{1,4}", union or ""):
            union = ""
        party = _joined("party")
        agency = _joined("agency")
        unit_columns = [
            _clean(" ".join(parts.get(role, [])))
            for role in roles
            if _base_role(role) == "unit"
        ]
        unit = "; ".join(chunk for chunk in unit_columns if chunk)

        employees = ""
        emp_match = re.search(r"(?<!\d)(\d{1,4})(?!\d)", date_line_employees or "")
        if emp_match:
            employees = emp_match.group(1)

        head = " ".join(block_lines[:6])
        if re.search(r"Majority\s+Interest", head, re.I) or (
            re.search(r"\bMajority\b", head, re.I)
            and re.search(r"\bInterest\b", head, re.I)
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
        elif code == "DE":
            canonical = "DESIGNATION_EXCLUDED"
        else:
            canonical = "CERTIFICATION"

        certified, employer, union, party = _heal_shredded_fields(
            certified=certified,
            employer=employer,
            union=union,
            party=party,
        )
        if union and re.search(r"(?i)[A-Za-z]{3,}", union):
            if (
                not party
                or len(union) >= len(party)
                or not re.search(r"(?i)[A-Za-z]{3,}", party)
            ):
                party = union[:80]

        case_number = "+".join(cases)
        rows.append(
            {
                "row_key": f"{AGENCY_CODE}:{fiscal_year}:{case_number}",
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "panel": "Local" if cases[0].startswith("L-") else "State",
                "fiscal_year": fiscal_year,
                "table_heading": heading[:160],
                "canonical_case_type": canonical,
                "native_case_type": native,
                "certified_date": certified,
                "employer_name": employer[:220],
                "agency": agency[:220],
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

    return _strip_neighbor_bleed(rows)


_TABLE_BANNER_RE = re.compile(
    r"CERTIFICATION|REVOCATION|AMENDMENT|CLARIFICATION|DESIGNATION|RECOGNIZED",
    re.I,
)


def _sub_sections(
    lines: list[str], start: int, end: int, heading: str
) -> list[tuple[str, int, int]]:
    """Split a header section at its inner table banners.

    Later tables in a volume sometimes reuse the previous table's column layout
    and print only a banner, with no header row of their own. They are still
    separate tables and must not share row state.
    """
    marks: list[tuple[str, int]] = [(heading, start)]
    for i in range(start, end):
        if not _is_banner(lines[i]) or not _TABLE_BANNER_RE.search(lines[i]):
            continue
        banner = [lines[i].strip()]
        j = i + 1
        while j < end and _is_banner(lines[j]):
            banner.append(lines[j].strip())
            j += 1
        marks.append((_clean_heading(" ".join(banner)), i))
    out: list[tuple[str, int, int]] = []
    for idx, (label, begin) in enumerate(marks):
        stop = marks[idx + 1][1] if idx + 1 < len(marks) else end
        if stop > begin:
            out.append((label, begin, stop))
    return out


def parse_certs_text(
    text: str,
    *,
    fiscal_year: str,
    pdf_url: str,
    scraped_at: str,
) -> list[dict[str, str]]:
    """Parse pdftotext -layout output for one FY certifications PDF."""
    lines = text.replace("\x0c", "").split("\n")
    sections = find_table_sections(lines)
    if not sections:
        return []

    rows: list[dict[str, str]] = []
    for idx, (heading, header_i, columns) in enumerate(sections):
        end = sections[idx + 1][1] if idx + 1 < len(sections) else len(lines)
        for label, begin, stop in _sub_sections(
            lines, header_i + 1, end, heading
        ):
            rows.extend(
                _parse_section(
                    lines[begin:stop],
                    columns,
                    label or heading,
                    fiscal_year=fiscal_year,
                    pdf_url=pdf_url,
                    scraped_at=scraped_at,
                )
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
