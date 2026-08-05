"""California PERB Decision Bank (WordPress REST).

WHAT THIS FILE IS FOR
---------------------
perb.ca.gov publishes Board / ALJ decisions as a WordPress custom post type
(`decision`). Paginate wp-json/wp/v2/decision (~4k posts), pull Description /
Disposition headnotes from rendered content, map jurisdiction suffixes (E/M/H/S/…)
and description keywords into the shared canonical_case_type enum, then write
a wide CSV.

Employer / union hints come from “Respondent …” / “Charging Party …” patterns in
the Description. PDFs are sparse on-site; source_url is the decision permalink.
MMBA city/county local boards (LA City ERB / LA County ERCOM) are out of scope.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urlencode

from perb_data_collection.http import fetch_url, strip_html_text
from perb_data_collection.csv_io import write_wide_csv

FLOW_NAME = "CA PERB Decisions Flow"
REPORT_PREFIX = "ca_perb_decisions"
AGENCY_CODE = "CA_PERB"
BASE_URL = "https://perb.ca.gov"
API_URL = f"{BASE_URL}/wp-json/wp/v2/decision"
PAGE_SIZE = 100

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "decision_number",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "jurisdiction_statute",
    "employer_name",
    "union_name",
    "document_title",
    "description",
    "disposition",
    "decision_date",
    "wp_post_id",
    "pdf_url",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)

# Decision-number jurisdictional suffix → statute (PERB's own Decision Bank letters).
_STATUTE_BY_SUFFIX = {
    "E": "EERA",
    "EA": "EERA",
    "M": "MMBA",
    "MA": "MMBA",
    "H": "HEERA",
    "HA": "HEERA",
    "S": "DILLS",
    "SA": "DILLS",
    "C": "TRIAL_COURT",
    "CA": "TRIAL_COURT",
    "I": "COURT_INTERPRETER",
    "IA": "COURT_INTERPRETER",
    "J": "JCEERA",
    "JA": "JCEERA",
    "P": "PECC",
    "PA": "PECC",
    "R": "TRANSIT",
    "RA": "TRANSIT",
    "N": "CHILD_CARE",
    "NA": "CHILD_CARE",
}

_EMPLOYER_HINTS = (
    "city",
    "county",
    "district",
    "state of",
    "school",
    "university",
    "college",
    "regents",
    "trustees",
    "town",
    "hospital",
    "commission",
    "authority",
    "bureau",
    "department",
    "municipal",
    "special district",
    "water district",
    "transit",
    "court",
)
_UNION_HINTS = (
    "union",
    "association",
    "federation",
    "afscme",
    "seiu",
    "cta",
    "nea",
    "cwa",
    "teamsters",
    "local ",
    "employee organization",
    "bargaining unit",
    "guild",
)

_CANONICAL_FROM_TEXT = (
    (re.compile(r"\bdecertif", re.I), "DECERTIFICATION"),
    (re.compile(r"\bseverance\b", re.I), "SEVERANCE"),
    (re.compile(r"\bunit modif|\bunit clarification\b", re.I), "UNIT_MODIFICATION"),
    (re.compile(r"\bamendment of certification\b", re.I), "AMENDMENT_OF_CERTIFICATION"),
    (re.compile(r"\brequest for recognition\b|\bvoluntary recognition\b", re.I), "RECOGNITION"),
    (re.compile(r"\bpetition for certification\b|\brepresentation election\b|\bcertification of", re.I), "CERTIFICATION"),
    (re.compile(r"\bfact[- ]find", re.I), "FACT_FINDING"),
    (re.compile(r"\bimpasse\b", re.I), "IMPASSE"),
    (re.compile(r"\bnegotiab", re.I), "NEGOTIABILITY"),
    (re.compile(r"\barbitrat", re.I), "ARBITRATION"),
    (re.compile(r"\bunfair practice\b|\bduty of fair representation\b|\bulp\b", re.I), "ULP"),
)

_DECISION_NUM_RE = re.compile(
    r"^(?P<prefix>A?)(?P<num>\d+)(?P<suffix>[A-Za-z]+)$",
    flags=re.I,
)
_RESPONDENT_RE = re.compile(
    r"Respondent\s+(.+?)\s+"
    r"(?:violated|breached|retaliated|by\b|and the|thereby|under the|"
    r"when it|because|for engaging|in its|in the)",
    flags=re.I | re.S,
)
_CHARGING_PARTY_RE = re.compile(
    r"Charging Part(?:y|ies)\s+(.+?)\s+"
    r"(?:alleged|appealed|filed|asserted|charged|each appealed)",
    flags=re.I | re.S,
)
# "alleged that the State of California (…) violated/retaliated"
_ALLEGED_THAT_RE = re.compile(
    r"alleged that(?:\s+the)?\s+(?:Respondent\s+)?(.+?)\s+"
    r"(?:violated|breached|retaliated|engaged|discriminat)\b",
    flags=re.I | re.S,
)
# "unfair practice charge against Trustees of …"
_AGAINST_RE = re.compile(
    r"(?:unfair practice charge|complaint)\s+against\s+(.+?)(?:\s*,|\s+alleging|\s+for\b|\s+claiming|\.|$)",
    flags=re.I | re.S,
)

def _api_page_url(*, page: int, per_page: int = PAGE_SIZE) -> str:
    qs = urlencode(
        {
            "per_page": per_page,
            "page": page,
            "orderby": "date",
            "order": "desc",
            "_fields": "id,slug,title,content,date,link",
        }
    )
    return f"{API_URL}?{qs}"

def _strip_strong_paragraph(content_html: str, label: str) -> str:
    pattern = re.compile(
        rf"<strong>\s*{re.escape(label)}\s*:</strong>\s*(.*?)</p>",
        flags=re.I | re.S,
    )
    match = pattern.search(content_html or "")
    if not match:
        return ""
    return strip_html_text(unescape(match.group(1)))

def _parse_decision_number(slug: str, title: str) -> tuple[str, str, str]:
    """Return (decision_number, statute, native_doc_kind)."""
    raw = (title or slug or "").strip()
    raw = re.sub(r"^Decision\s+", "", raw, flags=re.I).strip()
    token = raw.split()[0] if raw else slug
    token = token.upper().rstrip(".,;")
    match = _DECISION_NUM_RE.match(token) or _DECISION_NUM_RE.match((slug or "").upper())
    if not match:
        return token or slug.upper(), "", "DECISION"
    prefix = match.group("prefix").upper()
    num = match.group("num")
    suffix = match.group("suffix").upper()
    decision_number = f"{prefix}{num}{suffix}" if prefix else f"{num}{suffix}"
    # ALJ / admin appeals often use A###X; keep suffix letter for statute.
    statute_key = suffix
    if len(suffix) > 1 and suffix.endswith("A") and suffix[:-1] in _STATUTE_BY_SUFFIX:
        statute_key = suffix[:-1]
    statute = _STATUTE_BY_SUFFIX.get(statute_key, _STATUTE_BY_SUFFIX.get(suffix, ""))
    native = "ALJ_APPEAL" if prefix == "A" else "BOARD_DECISION"
    return decision_number, statute, native

def _looks_like_union(name: str) -> bool:
    lowered = name.lower()
    return any(h in lowered for h in _UNION_HINTS)

def _looks_like_employer(name: str) -> bool:
    lowered = name.lower()
    return any(h in lowered for h in _EMPLOYER_HINTS)

def _clean_party(name: str) -> str:
    text = re.sub(r"\s+", " ", name).strip(" ,.;")
    text = re.sub(r"\s*\([^)]{0,80}\)\s*$", "", text).strip()
    # Trim runaway captures
    if len(text) > 180:
        text = text[:180].rsplit(" ", 1)[0]
    return text

def _classify_party(name: str) -> str:
    """Return 'employer', 'union', or 'unknown'."""
    if not name:
        return "unknown"
    emp = _looks_like_employer(name)
    uni = _looks_like_union(name)
    if emp and not uni:
        return "employer"
    if uni and not emp:
        return "union"
    if emp and uni:
        # e.g. "District Employees Association" — prefer union.
        return "union"
    return "unknown"

def _parties_from_description(description: str) -> tuple[str, str]:
    """Return (employer_name, union_name) heuristics from Description prose."""
    respondent = ""
    charging = ""
    match = _RESPONDENT_RE.search(description)
    if match:
        respondent = _clean_party(match.group(1))
    match = _CHARGING_PARTY_RE.search(description)
    if match:
        charging = _clean_party(match.group(1))
    if not respondent:
        match = _ALLEGED_THAT_RE.search(description)
        if match:
            respondent = _clean_party(match.group(1))
    if not respondent:
        match = _AGAINST_RE.search(description)
        if match:
            respondent = _clean_party(match.group(1))

    employer = ""
    union = ""
    for name in (respondent, charging):
        kind = _classify_party(name)
        if kind == "employer" and not employer:
            employer = name
        elif kind == "union" and not union:
            union = name
    # Fallbacks when classifiers miss
    if not employer and respondent and _classify_party(respondent) != "union":
        employer = respondent
    if not union and charging and _classify_party(charging) == "union":
        union = charging
    if not employer and not union and respondent:
        if _classify_party(respondent) == "union":
            union = respondent
        else:
            employer = respondent
    return employer, union

def _jurisdiction_city(employer_name: str) -> str:
    name = employer_name.strip()
    name = re.sub(
        r"^(City|Town|County|Regents|Trustees)\s+of\s+(the\s+)?",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"^State of California\s*(?:\(|$)", "Sacramento", name, flags=re.I)
    return name.split(",")[0].strip()[:80]

def _canonical(description: str, disposition: str, document_title: str) -> str:
    blob = f"{description} {disposition} {document_title}"
    for pattern, canonical in _CANONICAL_FROM_TEXT:
        if pattern.search(blob):
            return canonical
    return "ULP"

def _candidate_pdf_url(slug: str) -> str:
    return f"{BASE_URL}/wp-content/uploads/decisionbank/decision-{slug.lower()}.pdf"

def parse_decision_post(post: dict[str, Any], *, scraped_at: str) -> dict[str, str] | None:
    post_id = str(post.get("id") or "").strip()
    slug = str(post.get("slug") or "").strip()
    if not post_id or not slug:
        return None
    title = strip_html_text(unescape((post.get("title") or {}).get("rendered") or ""))
    content = (post.get("content") or {}).get("rendered") or ""
    description = _strip_strong_paragraph(content, "Description")
    disposition = _strip_strong_paragraph(content, "Disposition")
    link = str(post.get("link") or f"{BASE_URL}/decision/{slug}/").strip()
    decision_date = str(post.get("date") or "")[:10]
    decision_number, statute, native_doc = _parse_decision_number(slug, title)
    employer, union = _parties_from_description(description)
    document_title = title or decision_number
    if employer and " – " not in document_title and " - " not in document_title:
        document_title = f"Decision {decision_number} – {employer}"
    pdf_url = _candidate_pdf_url(slug)
    row_key = f"{AGENCY_CODE}:{decision_number}:{post_id}"
    return {
        "row_key": row_key,
        "source_agency_code": AGENCY_CODE,
        "decision_number": decision_number,
        "case_number": decision_number,
        "canonical_case_type": _canonical(description, disposition, document_title),
        "native_case_type": native_doc,
        "jurisdiction_statute": statute,
        "employer_name": employer,
        "union_name": union,
        "document_title": document_title,
        "description": description[:4000],
        "disposition": disposition[:2000],
        "decision_date": decision_date,
        "wp_post_id": post_id,
        "pdf_url": pdf_url,
        "jurisdiction_city": _jurisdiction_city(employer),
        "jurisdiction_state": "CA",
        "employer_street": "",
        "employer_zip": "",
        "source_page_url": link,
        "source_url": link,
        "scraped_at": scraped_at,
    }

def parse_api_page(payload: list[Any], *, scraped_at: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for post in payload:
        if not isinstance(post, dict):
            continue
        row = parse_decision_post(post, scraped_at=scraped_at)
        if row:
            rows.append(row)
    return rows

def scrape_decisions(
    *,
    delay_seconds: float = 0.2,
    fetch_json: Any = None,
    page_size: int = PAGE_SIZE,
    max_pages: int | None = None,
) -> list[dict[str, str]]:
    """Paginate WordPress decision CPT until exhausted."""
    fetcher = fetch_json or (lambda url, **kwargs: fetch_url(url, **kwargs))
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break
        url = _api_page_url(page=page, per_page=page_size)
        raw = fetcher(url, delay_seconds=delay_seconds)
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, list) or not payload:
            break
        page_rows = parse_api_page(payload, scraped_at=scraped_at)
        for row in page_rows:
            if row["wp_post_id"] in seen:
                continue
            seen.add(row["wp_post_id"])
            rows.append(row)
        if len(payload) < page_size:
            break
        page += 1

    if not rows:
        raise RuntimeError(f"CA PERB Decision Bank API returned 0 posts: {API_URL}")
    rows.sort(key=lambda row: (row["decision_date"], row["decision_number"]), reverse=True)
    return rows

def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.2) -> int:
    rows = scrape_decisions(delay_seconds=delay_seconds)
    return write_wide_csv(rows, csv_path, fieldnames=WIDE_FIELDNAMES)

