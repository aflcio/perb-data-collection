"""Nebraska CIR Reporter decision index.

WHAT THIS FILE IS FOR
---------------------
Enumerate CIR Reporter volumes on nebraska.gov's reporter_and_appeals_search,
parse decision filenames for citation / year / party hints, enrich parties from
decision HTML captions when fetchable (infra-75), and land a wide index feed
through shared state-PERB ACE (GeoCensus).

Most CIR matters are wage/interest disputes rather than pure certifications;
`canonical_case_type` defaults to ARBITRATION with filename heuristics for
representation-ish language. Cadence is monthly (volume archive).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

from perb_data_collection.http import fetch_url
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "NE CIR Reporter Flow"
REPORT_PREFIX = "ne_cir_reporter"
AGENCY_CODE = "NE_CIR"
BASE_URL = "https://www.nebraska.gov"
INDEX_URL = (
    f"{BASE_URL}/ncir/reporter_and_appeals_search/index.cgi?type=reporter"
)

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "cir_volume",
    "cir_page",
    "decision_year",
    "employer_name",
    "union_name",
    "document_title",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

_VOLUME_RE = re.compile(
    r"index\.cgi\?dir=(\d+_CIR_xx)&type=reporter",
    flags=re.I,
)
_DECISION_HREF_RE = re.compile(
    r'href="([^"]*data/reporter/[^"]+\.html?)"',
    flags=re.I,
)
# 19_CIR_13_(2014)_NAPE_Local_61_NE_Dept._Corrections.htm
# 1_CIR_1_(1948).html
_FILENAME_RE = re.compile(
    r"^(?P<vol>\d+)_CIR_?(?P<page>\d+)__?\((?P<year>\d{4})\)(?:_(?P<rest>.+))?$",
    flags=re.I,
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
#: Filename / index tokens that are the respondent employer, not a union (infra-75).
_EMPLOYER_ONLY_UNION = re.compile(
    r"^(STATE OF NE(?:BRASKA)?|THE STATE OF NE(?:BRASKA)?)\b",
    re.I,
)
_EMPLOYER_CUES = re.compile(
    r"\b(city of|county of|state of|department|school district|village of|"
    r"public schools|board of education)\b",
    re.I,
)
_UNION_CUES = re.compile(
    r"\b(association|local\s+\d|afscme|iaff|fop|brotherhood|federation|"
    r"union|nape|teamsters|nebrask?a education)\b",
    re.I,
)


def _absolute_url(href: str) -> str:
    return urljoin(BASE_URL + "/", href)


def list_volume_dirs(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for vol in _VOLUME_RE.findall(html):
        key = vol.upper()
        if key in seen:
            continue
        seen.add(key)
        found.append(vol)
    # Stable numeric order.
    found.sort(key=lambda v: int(v.split("_", 1)[0]))
    return found


def volume_index_url(volume_dir: str) -> str:
    return (
        f"{BASE_URL}/ncir/reporter_and_appeals_search/index.cgi"
        f"?dir={volume_dir}&type=reporter"
    )


def list_decision_hrefs(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for href in _DECISION_HREF_RE.findall(html):
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(href)
    found.sort(key=str.lower)
    return found


def _split_parties(rest: str) -> tuple[str, str]:
    """Heuristic: last '_v_' / '_City_of_' chunk tends to be employer side."""
    text = rest.replace("__", "_")
    text = re.sub(r"_+", " ", text).strip()
    text = text.replace(" Ass n", " Ass'n").replace(" Int l", " Int'l")
    lowered = text.lower()
    for sep in (" v ", " vs "):
        if sep in lowered:
            idx = lowered.rfind(sep)
            left = text[:idx].strip(" -_")
            right = text[idx + len(sep) :].strip(" -_")
            return right, left  # employer, union guess
    city = re.search(
        r"(.+?)\s+(City of .+)$",
        text,
        flags=re.I,
    )
    if city:
        return city.group(2).strip(), city.group(1).strip()
    # Fallback: put full string as employer label for ACE city/state geocode of NE
    return text, ""


def _canonical_from_title(title: str) -> str:
    lowered = title.lower()
    if "decertif" in lowered:
        return "DECERTIFICATION"
    if any(k in lowered for k in ("certif", "represent", "election", "bargaining unit")):
        return "CERTIFICATION"
    return "ARBITRATION"


def _html_to_lines(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/tr|/li|/h[1-6]|/td)\b[^>]*>", "\n", html)
    text = _TAG.sub(" ", html)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        line = _WS.sub(" ", raw).strip(" \t,;")
        if line:
            lines.append(line)
    return lines


def parse_decision_caption(html: str) -> tuple[str, str] | None:
    """Return (employer_name, union_name) from a CIR decision body caption.

    Word-exported decisions put Petitioner / v. / Respondent in the body. Prefer
    that over filename abbreviations (infra-75).
    """
    lines = _html_to_lines(html)
    if not lines:
        return None

    start = 0
    for i, line in enumerate(lines):
        if "commission of industrial relations" in line.lower():
            start = i + 1
            break

    end = len(lines)
    for i in range(start, len(lines)):
        low = lines[i].lower()
        if low.startswith("case no") or "findings and order" in low or low.startswith(
            "nature of the case"
        ):
            end = i
            break

    caption = " ".join(lines[start:end])
    caption = _WS.sub(" ", caption).strip()
    if not caption:
        return None

    # Split on a standalone v. / vs. between parties.
    split = re.split(r"\bvs?\.?\b", caption, maxsplit=1, flags=re.I)
    if len(split) != 2:
        return None

    left = re.sub(r",?\s*petitioner\.?\s*$", "", split[0], flags=re.I).strip(" ,")
    right = re.sub(r",?\s*respondent\.?\s*$", "", split[1], flags=re.I).strip(" ,.")
    if not left or not right:
        return None

    # Default CIR shape: petitioner = union, respondent = employer.
    union, employer = left, right
    # If cues strongly reverse that, swap.
    if _EMPLOYER_CUES.search(left) and _UNION_CUES.search(right):
        employer, union = left, right
    elif _UNION_CUES.search(left) and _EMPLOYER_CUES.search(right):
        union, employer = left, right

    return employer[:240], union[:240]


def _scrub_employer_as_union(employer: str, union: str) -> tuple[str, str]:
    """Move known employer-only tokens out of union_name (infra-75)."""
    if union and _EMPLOYER_ONLY_UNION.match(union.strip()):
        if not employer or _EMPLOYER_ONLY_UNION.match(employer.strip()):
            return union.strip(), ""
        return employer, ""
    return employer, union


def parse_decision_filename(
    href: str,
    *,
    volume_dir: str,
    volume_page_url: str,
    scraped_at: str,
) -> dict[str, str] | None:
    name = unquote(href.rsplit("/", 1)[-1])
    stem = re.sub(r"\.html?$", "", name, flags=re.I)
    match = _FILENAME_RE.match(stem)
    if not match:
        # Still land a row with raw filename.
        case_number = stem.replace("_", " ")
        employer, union = _scrub_employer_as_union(case_number, "")
        return {
            "row_key": f"{AGENCY_CODE}:{stem[:120]}",
            "source_agency_code": AGENCY_CODE,
            "case_number": case_number[:80],
            "canonical_case_type": "ARBITRATION",
            "native_case_type": "CIR_REPORTER",
            "cir_volume": volume_dir.split("_", 1)[0],
            "cir_page": "",
            "decision_year": "",
            "employer_name": employer,
            "union_name": union,
            "document_title": stem,
            "jurisdiction_city": "",
            "jurisdiction_state": "NE",
            "employer_street": "",
            "employer_zip": "",
            "source_page_url": volume_page_url,
            "source_url": _absolute_url(href),
            "scraped_at": scraped_at,
        }

    vol = match.group("vol")
    page = match.group("page")
    year = match.group("year")
    rest = match.group("rest") or ""
    employer, union = _split_parties(rest) if rest else ("", "")
    employer, union = _scrub_employer_as_union(employer, union)
    if not employer and not union:
        employer = f"CIR Volume {vol} p.{page}"
    case_number = f"{vol} CIR {page} ({year})"
    title = unquote(stem)
    return {
        "row_key": f"{AGENCY_CODE}:{vol}_CIR_{page}_{year}",
        "source_agency_code": AGENCY_CODE,
        "case_number": case_number,
        "canonical_case_type": _canonical_from_title(title),
        "native_case_type": "CIR_REPORTER",
        "cir_volume": vol,
        "cir_page": page,
        "decision_year": year,
        "employer_name": employer,
        "union_name": union,
        "document_title": title,
        "jurisdiction_city": "",
        "jurisdiction_state": "NE",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": volume_page_url,
        "source_url": _absolute_url(href),
        "scraped_at": scraped_at,
    }


def enrich_row_from_decision_html(row: dict[str, str], html: str) -> dict[str, str]:
    """Prefer caption parties when the decision HTML parses cleanly."""
    parsed = parse_decision_caption(html)
    if not parsed:
        return row
    employer, union = _scrub_employer_as_union(*parsed)
    out = dict(row)
    if employer:
        out["employer_name"] = employer
    if union:
        out["union_name"] = union
    elif employer and _EMPLOYER_ONLY_UNION.match(row.get("union_name") or ""):
        out["union_name"] = ""
    return out


def scrape_reporter(
    *,
    delay_seconds: float = 0.25,
    fetch_html: Any = None,
    fetch_decision_bodies: bool = True,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    index_html = fetcher(INDEX_URL, delay_seconds=delay_seconds)
    volumes = list_volume_dirs(index_html)
    if not volumes:
        raise RuntimeError(f"NE CIR reporter index found 0 volumes: {INDEX_URL}")

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for volume_dir in volumes:
        page_url = volume_index_url(volume_dir)
        vol_html = fetcher(page_url, delay_seconds=delay_seconds)
        for href in list_decision_hrefs(vol_html):
            parsed = parse_decision_filename(
                href,
                volume_dir=volume_dir,
                volume_page_url=page_url,
                scraped_at=scraped_at,
            )
            if parsed is None:
                continue
            if parsed["row_key"] in seen_keys:
                continue
            seen_keys.add(parsed["row_key"])
            if fetch_decision_bodies:
                try:
                    decision_html = fetcher(
                        parsed["source_url"], delay_seconds=delay_seconds
                    )
                    parsed = enrich_row_from_decision_html(parsed, decision_html)
                except Exception:
                    # Filename parties remain; a single bad decision must not
                    # abort the volume harvest.
                    pass
            rows.append(parsed)

    if not rows:
        raise RuntimeError("NE CIR reporter volumes parsed 0 decisions")
    rows.sort(key=lambda row: (row["cir_volume"].zfill(3), row["cir_page"].zfill(5)))
    return rows


def scrape_to_wide_csv(
    csv_path: Any,
    *,
    delay_seconds: float = 0.25,
    fetch_decision_bodies: bool = True,
) -> int:
    rows = scrape_reporter(
        delay_seconds=delay_seconds,
        fetch_decision_bodies=fetch_decision_bodies,
    )
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)
