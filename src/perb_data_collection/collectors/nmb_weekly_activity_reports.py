"""National Mediation Board Weekly Activity Reports HTML collector.

Every week since 1998 the NMB posts a report listing the cases it opened,
settled and closed: mediation dockets (``A-`` Section 6 cases, ``GM-``
grievance mediation, ``T-`` and others), representation applications
(``R-``/``CR-``/``RD-``), ballots mailed, elections underway and closed cases.
Each table row names a carrier, an organisation and a craft or class.

A mediation docket is the Board mediating between a carrier and its employees'
representative, so it names the union that bargains for a craft at a carrier
even when that unit was organised decades before the determinations listing
begins.  See docs/research/agencies/nmb-weekly-activity-reports.md.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.http import fetch_url

logger = logging.getLogger(__name__)

FLOW_NAME = "NMB Weekly Activity Reports Flow"
REPORT_PREFIX = "nmb_weekly_activity_reports"
AGENCY_CODE = "NMB"
BASE_URL = "https://nmb.gov/NMB_Application/index.php/"
ARCHIVE_URL = f"{BASE_URL}archived-weekly-activity-reports/"
CURRENT_URL = f"{BASE_URL}weekly-activity-report-2/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key", "source_agency_code", "case_number", "case_prefix",
    "canonical_case_type", "native_case_type", "section",
    "employer_name", "union_name", "craft_class", "approx_employees",
    "status", "disposition", "count_date", "docket_date", "location",
    "mediator_or_investigator",
    "report_week_start", "report_week_end",
    "jurisdiction_city", "jurisdiction_state", "employer_street", "employer_zip",
    "source_page_url", "source_url", "scraped_at",
)

# Sections that carry case rows.  Order matters: the first pattern that
# matches a label wins, so the narrow ones come first.
_SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("arbitration", re.compile(r"arbitrat|abritrat|\bnrab\b|\bplb|\bsba|public law board|adjustment board", re.I)),
    ("mediation_new_docket", re.compile(r"new\s+docket|^\s*dockets?\s*:", re.I)),
    ("mediation_assigned", re.compile(r"assigned|reassigned", re.I)),
    ("mediation_settlement", re.compile(r"settlement|settled|ratif", re.I)),
    ("mediation_released", re.compile(r"proffer|release|cooling|strike|self[- ]help", re.I)),
    ("mediation_meeting", re.compile(r"meeting|session|conference|training|facilitation", re.I)),
    ("representation_application", re.compile(r"new\s+applications?|applications?\s+(?:received|docketed)", re.I)),
    ("ballots_mailed", re.compile(r"ballot", re.I)),
    ("election_authorized", re.compile(r"elections?\s+authorized", re.I)),
    ("election_underway", re.compile(r"elections?\s+underway|elections?\s+in\s+progress", re.I)),
    ("case_closed", re.compile(r"cases?\s+closed|closed\s+cases?|^\s*closed\s*:", re.I)),
    ("interference", re.compile(r"interference", re.I)),
)
_SKIPPED_SECTIONS = frozenset({"arbitration"})
# Headings that group sections without carrying rows of their own.
_SUPER_SECTION = re.compile(
    r"^\s*(?:mediation(?:\s+and\s+alternative\s+dispute\s+resolution|\s*/\s*adr)?|representation|"
    r"weekly\s+activity\s+report|nmb\s+weekly\s+activity\s+report|officer\s+of\s+the\s+week\s+report)\s*:?\s*$",
    re.I,
)

# "A-13586", "A12882" (1998, no dash), "A-12897-99" (a range: 12897 to 12899).
_CASE_TOKEN = re.compile(
    r"\b([A-Z]{1,3})\s*(?:[-\u2013]\s*(\d{2,5})|(\d{3,5}))(?:\s*[-\u2013]\s*(\d{1,3})\b(?!/))?"
)
# Series printed both padded and unpadded; A-, R- and CR- numbers are always 4-5 digits.
_PADDED_PREFIXES = frozenset({"GM", "T", "F", "OP", "TF"})
# 2011 and 2020 mediation tables sometimes drop the prefix: "13476" is A-13476.
_BARE_MEDIATION_CASE = re.compile(r"^\s*(1\d{4})\s*$")
_MEDIATION_SECTIONS = frozenset({
    "mediation_new_docket", "mediation_assigned", "mediation_settlement", "mediation_released", "mediation_meeting",
})
MAX_CASE_RANGE = 12
_DATE_TOKEN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_MONTHS = {
    name: index
    for index, names in enumerate(
        (("jan", "january", "janurary"), ("feb", "february", "febuary"), ("mar", "march"), ("apr", "april"),
         ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
         ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")),
        start=1,
    )
    for name in names
}
_MONTH_DAY = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*((?:19|20)\d{2}))?",
    re.I,
)

# The canonical enum has no mediation type, so only representation applications map.
_CANONICAL_BY_SECTION = {
    "representation_application": "CERTIFICATION",
    "ballots_mailed": "CERTIFICATION",
    "election_underway": "CERTIFICATION",
}


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _key_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", _normalise(value).upper()).strip("-")


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


_LABEL_LIKE = re.compile(r"^[A-Za-z][A-Za-z ,/&'().\u2019-]{2,60}:\s*(?:none\b.*|n/a)?$", re.I)


def is_section_label(text: str) -> bool:
    """A short heading such as "Ratifications:" or "REPRESENTATION" (not prose, not a date line)."""
    text = _normalise(text)
    return bool(_LABEL_LIKE.match(text)) and not _MONTH_DAY.search(text)


def classify_section(label: str) -> str:
    """Map a section label ("New Dockets:", "Elections Underway:") to a section key, or ""."""
    text = _normalise(label)
    if not text or len(text) > 120:
        return ""
    for key, pattern in _SECTION_PATTERNS:
        if pattern.search(text):
            return key
    return ""


# ---------------------------------------------------------------------------
# Report page structure
# ---------------------------------------------------------------------------


class _ReportParser(HTMLParser):
    """Flatten a report's entry content into text blocks and table rows, in order.

    Emits ``("text", str)`` for each run of text outside a table,
    ``("row", [cells])`` for each table row, and ``("table_end", "")``.
    """

    _BLOCK_TAGS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "table"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, Any]] = []
        self.title = ""
        self._in_title = False
        self._table_depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._text: list[str] = []
        self._skip_depth = 0

    def _flush_text(self) -> None:
        text = _normalise("".join(self._text))
        self._text = []
        if text:
            self.events.append(("text", text))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "table":
            if self._table_depth == 0:
                self._flush_text()
            self._table_depth += 1
        elif self._table_depth and tag == "tr":
            self._row = []
        elif self._table_depth and tag in {"td", "th"}:
            self._cell = []
        elif tag == "br":
            if self._cell is not None:
                self._cell.append(" ")
            elif not self._table_depth:
                self._flush_text()
        elif not self._table_depth and tag in self._BLOCK_TAGS:
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
        if self._table_depth and tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(_normalise("".join(self._cell)))
            self._cell = None
        elif self._table_depth and tag == "tr" and self._row is not None:
            if any(self._row):
                self.events.append(("row", self._row))
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self.events.append(("table_end", ""))
        elif not self._table_depth and tag in self._BLOCK_TAGS:
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        if self._cell is not None:
            self._cell.append(data)
        elif not self._table_depth:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush_text()


def _entry_content(html: str) -> str:
    """The WordPress post body; sidebars and menus repeat unrelated links."""
    match = re.search(r'class="[^"]*entry-content[^"]*"(.*?)(?:<!--\s*\.entry-content\s*-->|<footer|id="secondary")', html, re.S)
    return match.group(1) if match else html


# Header synonyms.  Keys are _header_key() of the printed label.
_COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "case": ("caseno", "case", "casenos", "caseno_s", "casenumber", "casenodocketdate", "docketno", "docket"),
    "carrier": ("carrier", "carriers", "employer", "carrierrailroad", "carrierairline"),
    "org": ("org", "orgs", "organization", "organizations", "union", "unions", "orgcraftorclass"),
    "craft": ("classcraft", "craftorclass", "craftclass", "craftandclass", "class", "craft"),
    "approx_craft": (),  # "Approx. No. of Emp.-Craft or Class" — matched by prefix below
    "status": ("status", "closing"),
    "disposition": ("disposition",),
    "count_date": ("countdate", "tallydate", "count"),
    "location": ("location", "site", "city"),
    "staff": ("mediators", "mediator", "investigator", "investigators", "srhearingofficer", "hearingofficer"),
}


def _map_header(cells: list[str]) -> dict[str, int] | None:
    """Return column indexes when ``cells`` is a case-table header row, else None."""
    indexes: dict[str, int] = {}
    for index, label in enumerate(cells):
        key = _header_key(label)
        if not key:
            continue
        if key.startswith("approx"):
            indexes.setdefault("approx_craft", index)
            continue
        if key.startswith("caseno") or key.startswith("case"):
            indexes.setdefault("case", index)
            if "docketdate" in key:
                indexes.setdefault("docket_date_in_case", index)
            continue
        if key == "docketdate":
            indexes.setdefault("docket_date", index)
            continue
        if key.startswith("carrier") and ("craft" in key or "class" in key):
            # "Carrier (Craft/Class)" (2001-2002): "Air Wisconsin (Mechanics)"
            indexes.setdefault("carrier", index)
            indexes.setdefault("carrier_craft", index)
            continue
        if key.startswith("org") and "craft" in key:
            # "Org./Craft or Class" (current mediation tables): "AFA / Flight Attendants"
            indexes.setdefault("org_craft", index)
            continue
        for column, synonyms in _COLUMN_SYNONYMS.items():
            if key in synonyms:
                indexes.setdefault(column, index)
                break
        else:
            if "craft" in key or key.endswith("class"):
                # "Proposed Craft or Class" (1998 applications)
                indexes.setdefault("craft", index)
    if "case" in indexes and "carrier" in indexes:
        return indexes
    return None


_POSITIONAL_HEADERS: dict[str, dict[str, int]] = {
    "mediation_new_docket": {"case": 0, "carrier": 1, "org": 2, "craft": 3, "staff": 4},
    "mediation_assigned": {"case": 0, "carrier": 1, "org": 2, "craft": 3, "staff": 4},
    "mediation_settlement": {"case": 0, "carrier": 1, "org": 2, "status": 3, "staff": 4},
    "mediation_released": {"case": 0, "carrier": 1, "org": 2, "status": 3, "staff": 4},
    "representation_application": {"case": 0, "carrier": 1, "org": 2, "approx_craft": 3, "staff": 4},
    "ballots_mailed": {"case": 0, "carrier": 1, "org": 2, "approx_craft": 3, "staff": 4},
    "election_underway": {"case": 0, "carrier": 1, "org": 2, "approx_craft": 3, "count_date": 4, "staff": 5},
    "case_closed": {"case": 0, "carrier": 1, "org": 2, "craft": 3, "disposition": 4},
}


def _cell(row: list[str], indexes: dict[str, int], key: str) -> str:
    index = indexes.get(key)
    return row[index] if index is not None and index < len(row) else ""


_APPROX = re.compile(r"^\s*(?:approx\.?\s*)?([\d,]+)\s*[-\u2013\u2014:]?\s*(.*)$", re.I)


def split_approx_craft(value: str) -> tuple[str, str]:
    """"335-Mechanics and Related Employees" -> ("335", "Mechanics and Related Employees")."""
    text = _normalise(value)
    match = _APPROX.match(text)
    if match and match.group(2):
        return match.group(1).replace(",", ""), _normalise(match.group(2))
    return "", text


def _split_org_craft(value: str) -> tuple[str, str]:
    text = _normalise(value)
    for separator in (" / ", "/", " - ", " \u2013 ", " \u2014 "):
        if separator in text:
            org, craft = text.split(separator, 1)
            return _normalise(org), _normalise(craft)
    return text, ""


_ORG_THEN_CRAFT = re.compile(r"^([A-Z][A-Z0-9&.\-]{1,14})\s*/\s*([A-Z][a-z].*)$")


def _split_carrier_craft(value: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", _normalise(value))
    return (_normalise(match.group(1)), _normalise(match.group(2))) if match else (_normalise(value), "")


def _to_iso(month: int, day: int, year: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _slash_date(value: str) -> str:
    match = _DATE_TOKEN.search(value or "")
    if not match:
        return ""
    month, day, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000 if year < 70 else 1900
    return _to_iso(month, day, year)


def parse_report_week(*texts: str) -> tuple[str, str]:
    """Return (week_start, week_end) ISO dates from a report heading, title or URL slug.

    Handles "November 15 — November 19, 2010", "Week Ending July 9, 1999",
    "December 29, 2025 – January 2, 2026" and slugs like
    ``weekly-activity-report-july-5-9-2004``.
    """
    for text in texts:
        if not text:
            continue
        candidate = re.sub(r"[-_/]+", " ", text) if "://" in text or re.fullmatch(r"[\w\-/.:]+", text) else text
        found: list[tuple[int, int, int | None]] = []
        for match in _MONTH_DAY.finditer(candidate):
            found.append((_MONTHS[match.group(1).lower().rstrip(".")], int(match.group(2)), int(match.group(3)) if match.group(3) else None))
        # "September 4-8, 2006", "December 20 through 24, 1999", slug "july 5 9 2004":
        # a bare day after the first month/day.
        if len(found) == 1 and found[0][2] is None:
            first = _MONTH_DAY.search(candidate)
            tail = re.match(
                r"\s*(?:-|\u2013|\u2014|through|thru|to)?\s*(\d{1,2})\s*,?\s*((?:19|20)\d{2})\b",
                candidate[first.end():],
                re.I,
            ) if first else None
            if tail:
                month = found[0][0]
                found = [(month, found[0][1], int(tail.group(2))), (month, int(tail.group(1)), int(tail.group(2)))]
        if not found or all(year is None for _m, _d, year in found):
            continue
        # Fill a missing year from the next date that carries one.
        resolved: list[str] = []
        for position, (month, day, year) in enumerate(found[:2]):
            if year is None:
                year = next((later for _m, _d, later in found[position + 1:] if later), None)
                if year is None:
                    continue
                if found[position + 1:] and month > found[position + 1][0]:
                    year -= 1  # "December 29 - January 2, 2026"
            iso = _to_iso(month, day, year)
            if iso:
                resolved.append(iso)
        if not resolved:
            continue
        if re.search(r"week\s+ending", candidate, re.I) or len(resolved) == 1:
            return "", resolved[0]
        return resolved[0], resolved[-1]
    return "", ""


def _split_cases(value: str) -> list[tuple[str, str, str]]:
    """Case numbers in a cell as (case_number, prefix, docket_date)."""
    docket_date = _slash_date(value)
    cases: list[tuple[str, str, str]] = []
    # A docket date printed in the same cell ("R-7626 10/02/24") is not a case.
    text = _DATE_TOKEN.sub(" ", value.upper())
    for prefix, dashed, undashed, range_end in _CASE_TOKEN.findall(text):
        number = dashed or undashed
        if prefix in _PADDED_PREFIXES:
            number = number.zfill(4)  # "GM-83" and "GM-0083", "T-515" and "T-0515" are one series
        numbers = [number]
        if range_end and len(range_end) < len(number):
            last = int(number[: len(number) - len(range_end)] + range_end)
            if 0 < last - int(number) <= MAX_CASE_RANGE:
                numbers = [str(n).zfill(len(number)) for n in range(int(number), last + 1)]
        cases.extend((f"{prefix}-{n}", prefix, docket_date) for n in numbers)
    return cases


def _regroup_vertical_tables(events: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Rebuild tables printed one cell per row (May 1999: "Case No.", "Carrier", ... then values).

    A run of single-cell rows whose first k cells form a case-table header is
    regrouped into rows of k cells.  Anything else passes through unchanged.
    """
    out: list[tuple[str, Any]] = []
    run: list[tuple[str, Any]] = []

    def flush() -> None:
        cells = [payload[0] for _kind, payload in run]
        for width in range(4, 8):
            if len(cells) >= 2 * width and len(cells) % width == 0 and _map_header(cells[:width]):
                out.extend(("row", cells[start:start + width]) for start in range(0, len(cells), width))
                break
        else:
            out.extend(run)
        run.clear()

    for event in events:
        kind, payload = event
        if kind == "row" and len(payload) == 1:
            run.append(event)
            continue
        if run:
            flush()
        out.append(event)
    if run:
        flush()
    return out


def parse_report(
    html: str,
    *,
    source_url: str,
    source_page_url: str,
    scraped_at: str,
    stats: Counter[str] | None = None,
) -> list[dict[str, str]]:
    """Parse one weekly report into wide rows (one per section x table row x case)."""
    stats = stats if stats is not None else Counter()
    if re.search(r"<title>\s*Page not found", html, re.I):
        stats["dead_report_links"] += 1
        logger.warning("NMB weekly report link is dead: %s", source_url)
        return []
    parser = _ReportParser()
    parser.feed(_entry_content(html))
    parser.close()
    head_text = " ".join(text for kind, text in parser.events[:6] if kind == "text")
    week_start, week_end = parse_report_week(head_text, parser.title, source_url)
    if not week_end:
        whole = _ReportParser()
        whole.feed(html)
        whole.close()
        week_start, week_end = parse_report_week(whole.title, source_url)
    if not week_end:
        stats["reports_without_week"] += 1
        logger.warning("NMB weekly report: no report week in %s", source_url)

    events = _regroup_vertical_tables(parser.events)
    section = section_label = ""
    header: dict[str, int] | None = None
    previous: dict[str, str] | None = None
    rows: list[dict[str, str]] = []
    tables = 0
    for kind, payload in events:
        if kind == "text":
            found = classify_section(payload)
            if found:
                section, header, previous, section_label = found, None, None, payload
            elif is_section_label(payload) and not _SUPER_SECTION.match(payload):
                # An unrecognised heading must not leave its rows filed under
                # the section above it ("Ratifications:" after "New Dockets: None").
                section, header, previous, section_label = "unclassified", None, None, payload
                stats[f"unclassified_label:{_normalise(payload)[:60]}"] += 1
            continue
        if kind == "table_end":
            # Keep the header: 1998 reports print it as its own one-row table
            # directly above the data table.  A new section label resets it.
            tables += 1
            previous = None
            continue
        cells: list[str] = payload
        filled = [cell for cell in cells if cell]
        mapped = _map_header(cells)
        if mapped is not None:
            header, previous = mapped, None
            continue
        if len(filled) == 1 and not _CASE_TOKEN.search(filled[0].upper()):
            found = classify_section(filled[0])
            if found:
                section, header, previous, section_label = found, None, None, filled[0]
            elif is_section_label(filled[0]) and not _SUPER_SECTION.match(filled[0]):
                section, header, previous, section_label = "unclassified", None, None, filled[0]
                stats[f"unclassified_label:{_normalise(filled[0])[:60]}"] += 1
            continue
        if section in _SKIPPED_SECTIONS:
            continue
        if header is None and len(cells) >= 4 and _CASE_TOKEN.search(cells[0].upper()):
            # 1998 tables often print no header row; fall back to the column
            # order every headed table of that section uses.
            header = _POSITIONAL_HEADERS.get(section)
            if header is not None:
                stats["positional_tables"] += 1
        if header is None:
            continue
        if not section:
            stats["rows_without_section"] += 1
            continue
        case_cell = _cell(cells, header, "case")
        cases = _split_cases(case_cell)
        bare = _BARE_MEDIATION_CASE.match(case_cell)
        if not cases and bare and section in _MEDIATION_SECTIONS:
            cases = [(f"A-{bare.group(1)}", "A", "")]
            stats["bare_mediation_case_numbers"] += 1
        carrier = _cell(cells, header, "carrier")
        org = _cell(cells, header, "org")
        craft = _cell(cells, header, "craft")
        approx = ""
        if "approx_craft" in header:
            approx, craft = split_approx_craft(_cell(cells, header, "approx_craft"))
        if "org_craft" in header:
            org, craft = _split_org_craft(_cell(cells, header, "org_craft"))
        if "carrier_craft" in header:
            carrier, craft = _split_carrier_craft(carrier)
        if not craft and "craft" not in header:
            # "BLET/Locomotive Engineers" in an Org. column (2020s ratification tables)
            split = _ORG_THEN_CRAFT.match(org)
            if split:
                org, craft = split.group(1).strip(), split.group(2).strip()
        if not cases:
            # A continuation row: the case, carrier and sometimes the org are on
            # the row above (one case, several organisations or crafts).
            if previous is not None and (org or craft or carrier):
                cases = [(previous["case_number"], previous["case_prefix"], previous["docket_date"])]
                carrier = carrier or previous["employer_name"]
                org = org or previous["union_name"]
                stats["continuation_rows"] += 1
            else:
                stats["rows_without_case"] += 1
                logger.debug("NMB weekly report %s: row without a case number: %s", source_url, cells)
                continue
        docket_date = _slash_date(_cell(cells, header, "docket_date")) if "docket_date" in header else ""
        for case_number, prefix, cell_docket_date in cases:
            row = {
                "source_agency_code": AGENCY_CODE,
                "case_number": case_number,
                "case_prefix": prefix,
                "canonical_case_type": _CANONICAL_BY_SECTION.get(section, ""),
                "native_case_type": _normalise(section_label).rstrip(":").strip()[:120],
                "section": section,
                "employer_name": carrier,
                "union_name": org,
                "craft_class": craft,
                "approx_employees": approx,
                "status": _cell(cells, header, "status"),
                "disposition": _cell(cells, header, "disposition"),
                "count_date": _slash_date(_cell(cells, header, "count_date")),
                "docket_date": docket_date or cell_docket_date,
                "location": _cell(cells, header, "location"),
                "mediator_or_investigator": _cell(cells, header, "staff"),
                "report_week_start": week_start,
                "report_week_end": week_end,
                "jurisdiction_city": "", "jurisdiction_state": "", "employer_street": "", "employer_zip": "",
                "source_page_url": source_page_url,
                "source_url": source_url,
                "scraped_at": scraped_at,
            }
            rows.append(row)
            previous = row
            stats[f"section:{section}"] += 1
    if tables == 0:
        stats["reports_without_tables"] += 1
    return rows


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_YEAR_PAGE = re.compile(r"(?:19|20)\d{2}-weekly-activity-reports?/?$", re.I)
_REPORT_LINK = re.compile(r"weekly-activity-report-(?!2/?$)[^/]*(?:19|20)\d{2}[^/]*/?$", re.I)


def discover_year_page_urls(archive_html: str) -> list[str]:
    """Year pages linked from the archive; their paths drift (``2023-weekly-activity-report/``,
    ``archived-weekly-activity-reports/2024-weekly-activity-reports/``)."""
    links = re.findall(r'href=["\']([^"\']+)["\']', archive_html, re.I)
    urls = {urljoin(ARCHIVE_URL, href) for href in links if _YEAR_PAGE.search(href.split("?")[0])}
    return sorted(urls, key=lambda url: (re.search(r"((?:19|20)\d{2})-weekly", url).group(1), url))


_ANCHOR = re.compile(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_REPORT_TEXT = re.compile(r"weekly\s+activity\s+report|week\s+ending", re.I)


def discover_report_urls(index_html: str, *, index_url: str) -> list[str]:
    """Report pages linked from a year page or the current-year index, in page order.

    Most slugs name the week (``weekly-activity-report-july-5-9-2004``) but some
    are bare post ids (``19048-2/``), so the link text counts as well.
    """
    body = _entry_content(index_html)
    seen: set[str] = set()
    urls: list[str] = []
    for href, anchor in _ANCHOR.findall(body):
        url = urljoin(index_url, href).split("#")[0]
        path = url.split("?")[0].rstrip("/")
        if not url.startswith(BASE_URL) or "wp-json" in url or "/wp-content/" in url:
            continue
        if _YEAR_PAGE.search(path + "/") or path + "/" in {ARCHIVE_URL, CURRENT_URL}:
            continue
        anchor_text = _normalise(re.sub(r"<[^>]+>", " ", anchor))
        if not (_REPORT_LINK.search(path + "/") or _REPORT_TEXT.search(anchor_text)):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _assign_row_keys(rows: list[dict[str, str]]) -> None:
    """``NMB-WAR:{week_end}:{section}:{case}:{org}:{craft}`` plus an ordinal on repeats.

    The same case can appear twice in one section of one week (one carrier,
    two crafts printed identically, or a report repeated under two URLs); the
    ordinal keeps the key unique without dropping a printed row.
    """
    counts: Counter[str] = Counter()
    for row in rows:
        base = ":".join((
            f"{AGENCY_CODE}-WAR",
            _key_part(row["report_week_end"] or "UNDATED"),
            _key_part(row["section"]),
            _key_part(row["case_number"]),
            _key_part(row["union_name"]) or "NO-ORG",
            _key_part(row["craft_class"]) or "NO-CRAFT",
        ))
        counts[base] += 1
        row["row_key"] = base if counts[base] == 1 else f"{base}:{counts[base]}"


_CONTENT_COLUMNS = ("report_week_end", "section", "case_number", "employer_name", "union_name", "craft_class", "status")


def scrape_weekly_reports(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    index_pages = [*discover_year_page_urls(fetcher(ARCHIVE_URL, delay_seconds=delay_seconds)), CURRENT_URL]
    if len(index_pages) < 2:
        raise RuntimeError(f"NMB weekly report archive exposed no year pages: {ARCHIVE_URL}")
    reports: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index_url in index_pages:
        found = discover_report_urls(fetcher(index_url, delay_seconds=delay_seconds), index_url=index_url)
        if not found:
            logger.warning("NMB weekly reports: no report links on %s", index_url)
        for url in found:
            if url not in seen:
                seen.add(url)
                reports.append((index_url, url))
    if not reports:
        raise RuntimeError("NMB weekly report scrape found 0 reports")
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    stats: Counter[str] = Counter()
    rows: list[dict[str, str]] = []
    seen_reports: dict[tuple[tuple[str, ...], ...], str] = {}
    for index_url, url in reports:
        try:
            html = fetcher(url, delay_seconds=delay_seconds)
        except Exception as exc:  # one missing week must not sink 28 years
            stats["reports_failed"] += 1
            logger.warning("NMB weekly reports: could not fetch %s: %s", url, exc)
            continue
        parsed = parse_report(html, source_url=url, source_page_url=index_url, scraped_at=scraped_at, stats=stats)
        # NMB sometimes posts one week's report under a second URL (the
        # "march-11-15-2024" page carries the March 18-22 report).
        signature = tuple(sorted(tuple(row[column] for column in _CONTENT_COLUMNS) for row in parsed))
        if parsed and signature in seen_reports:
            stats["duplicate_reports"] += 1
            logger.warning("NMB weekly reports: %s repeats %s", url, seen_reports[signature])
            continue
        seen_reports[signature] = url
        rows.extend(parsed)
    if not rows:
        raise RuntimeError("NMB weekly report scrape parsed 0 rows")
    if stats["reports_failed"] > max(5, len(reports) // 20):
        raise RuntimeError(f"NMB weekly reports: {stats['reports_failed']} of {len(reports)} reports failed to fetch")
    rows.sort(key=lambda row: (row["report_week_end"], row["section"], row["case_number"], row["union_name"], row["craft_class"], row["source_url"]))
    _assign_row_keys(rows)
    if len({row["row_key"] for row in rows}) != len(rows):
        raise RuntimeError("NMB weekly report scrape produced duplicate row keys")
    logger.info(
        "NMB weekly reports: %d reports, %d rows, %d distinct cases; %s",
        len(reports), len(rows), len({row["case_number"] for row in rows}),
        ", ".join(f"{key}={value}" for key, value in sorted(stats.items())),
    )
    return rows


def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3) -> int:
    return write_wide_csv(
        scrape_weekly_reports(delay_seconds=delay_seconds),
        csv_path,
        fieldnames=WIDE_FIELDNAMES,
    )
