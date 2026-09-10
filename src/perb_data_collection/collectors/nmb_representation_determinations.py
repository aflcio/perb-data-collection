"""National Mediation Board representation determinations HTML collector."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from perb_data_collection.csv_io import write_wide_csv
from perb_data_collection.http import fetch_bytes, fetch_url

logger = logging.getLogger(__name__)

FLOW_NAME = "NMB Representation Determinations Flow"
REPORT_PREFIX = "nmb_representation_determinations"
AGENCY_CODE = "NMB"
BASE_URL = "https://nmb.gov/NMB_Application/index.php/"
LISTING_URL = f"{BASE_URL}agency-determinations/"

WIDE_FIELDNAMES: tuple[str, ...] = (
    "row_key", "source_agency_code", "case_number", "case_cross_references",
    "canonical_case_type", "native_case_type", "employer_name", "union_name",
    "applicant_union", "certified_representative", "certification_text_snippet",
    "representation_asserted",
    "craft_class", "nmb_volume_number", "page_cite", "determination_date",
    "fiscal_year", "jurisdiction_city", "jurisdiction_state", "employer_street",
    "employer_zip", "source_page_url", "source_url", "scraped_at",
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _key_part(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", _normalise(value).upper()).strip("-")


def _fiscal_year_from_url(url: str) -> str:
    match = re.search(r"(?:fy)?(19\d{2}|20\d{2})-determinations/?$", url, re.I)
    return match.group(1) if match else ""


# A determination only *asserts* that a union now represents the craft when the
# Board actually certified a representative.  Everything else on the NMB
# disposition list -- dismissals, withdrawals, revocations, jurisdiction and
# single-carrier findings, transfers of an existing certification, denied
# appeals -- must not be landed as representation.  See the disposition
# inventory in docs/research/agencies/nmb-representation-determinations.md.
_NON_CERTIFICATION_MARKERS: tuple[str, ...] = (
    "transfer", "revocation", "revoke", "decert", "dismiss", "denied", "deny",
    "withdraw", "extinguish", "not subject", "not confirmed", "re-run", "rerun",
)
_CERTIFICATION_WORD = re.compile(r"\bcertif(?:ication|ications|ies|ied|y)\b|\bcert\b", re.I)


def _is_certification_disposition(disposition: str) -> bool:
    text = _normalise(disposition).lower()
    if not text:
        return False
    if any(marker in text for marker in _NON_CERTIFICATION_MARKERS):
        return False
    return bool(_CERTIFICATION_WORD.search(text))


def _canonical_case_type(disposition: str) -> str:
    return "CERTIFICATION" if _is_certification_disposition(disposition) else ""


# NMB certification pages close with a fixed sentence:
#   "... the Board certifies that the Transport Workers Union of America has
#    been duly designated and authorized to represent for the purposes of the
#    RLA ..."  (R-6952, 31 NMB No. 15; identical shape in R-7634 / 52 NMB No. 1
#   and R-7340 / 40 NMB No. 22).  pdftotext -layout wraps it across lines, so
#   the text is whitespace-collapsed before matching.
_CERTIFICATION_SENTENCE = re.compile(
    r"(?:the\s+Board\s+)?(?:hereby\s+)?certifies\s+that\s+(?:the\s+)?"
    r"(?P<org>.+?)\s+(?:has|have)\s+been\s+duly\s+designated\s+and\s+"
    r"authorized\s+to\s+represent",
    re.I,
)
MAX_CERTIFIED_REPRESENTATIVE = 200
MAX_CERTIFICATION_SNIPPET = 300


def parse_certification_sentence(text: str) -> tuple[str, str]:
    """Return (certified_representative, certification_text_snippet) or ("", "")."""
    collapsed = _normalise(text or "")
    if not collapsed:
        return "", ""
    match = _CERTIFICATION_SENTENCE.search(collapsed)
    if not match:
        return "", ""
    organization = _normalise(match.group("org")).strip(" ,;.")
    if not organization or len(organization) > MAX_CERTIFIED_REPRESENTATIVE:
        return "", ""
    return organization, match.group(0)[:MAX_CERTIFICATION_SNIPPET]


def default_pdf_to_text(payload: bytes) -> str:
    """pdftotext -l 3 -layout over an in-memory PDF."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "determination.pdf"
        pdf_path.write_bytes(payload)
        result = subprocess.run(
            ["pdftotext", "-l", "3", "-layout", str(pdf_path), "-"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext failed: {result.stderr.decode(errors='replace')[:200]}")
        return result.stdout.decode("utf-8", errors="replace")


class _TableParser(HTMLParser):
    """Dependency-free first-table parser that keeps a cell's document link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, str]]] = []
        self._in_table = self._in_row = False
        self._cell: list[str] | None = None
        self._row: list[tuple[str, str]] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table" and not self._in_table:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row, self._row = True, []
        elif self._in_row and tag in {"td", "th"}:
            self._cell, self._href = [], ""
        elif self._cell is not None and tag == "a":
            self._href = dict(attrs).get("href") or ""
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            self._row.append((_normalise("".join(self._cell)), self._href))
            self._cell = None
        elif tag == "tr" and self._in_row:
            if self._row:
                self.rows.append(self._row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            self._in_table = False


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _header_indexes(header: list[tuple[str, str]]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, (label, _href) in enumerate(header):
        key = _header_key(label)
        if key in {"pagecite", "date", "case", "carrier", "union", "craftclass", "disposition"}:
            indexes[key] = index
        if re.fullmatch(r"\d+nmbnumber", key):
            indexes["nmbnumber"] = index
    missing = {"pagecite", "date", "case", "carrier", "union", "craftclass", "disposition"} - set(indexes)
    if missing:
        raise RuntimeError(f"NMB table headers missing: {', '.join(sorted(missing))}")
    return indexes


def _cell(row: list[tuple[str, str]], indexes: dict[str, int], key: str) -> tuple[str, str]:
    index = indexes.get(key)
    return row[index] if index is not None and index < len(row) else ("", "")


def _document_href(row: list[tuple[str, str]], indexes: dict[str, int]) -> str:
    """The row's determination document link.

    Older year pages hang it off ``Page Cite``; FY2024+ pages hang it off the
    ``{vol} NMB Number`` cell instead.  Fall back to the first linked cell.
    """
    for key in ("pagecite", "nmbnumber"):
        href = _cell(row, indexes, key)[1]
        if href:
            return href
    return next((href for _text, href in row if href), "")


def parse_determinations_table(html: str, *, source_page_url: str, scraped_at: str) -> list[dict[str, str]]:
    parser = _TableParser()
    parser.feed(html)
    if len(parser.rows) < 2:
        return []
    indexes = _header_indexes(parser.rows[0])
    fiscal_year = _fiscal_year_from_url(source_page_url)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in parser.rows[1:]:
        case_number, _ = _cell(raw, indexes, "case")
        primary_case_number = _normalise(re.sub(r"\s*\([^)]*\)", "", case_number))
        craft_class, _ = _cell(raw, indexes, "craftclass")
        if not primary_case_number or not craft_class:
            continue
        page_cite, _page_cite_href = _cell(raw, indexes, "pagecite")
        pdf_href = _document_href(raw, indexes)
        # NMB can issue more than one determination for the same case and
        # craft.  The Board's volume/page cite and determination date
        # distinguish those events; fiscal-year pages are only an index, not
        # the source grain.
        determination_date, _ = _cell(raw, indexes, "date")
        row_key = (
            f"{AGENCY_CODE}:{_key_part(primary_case_number)}:"
            f"{_key_part(craft_class)}:{_key_part(page_cite)}:"
            f"{_key_part(determination_date)}"
        )
        if row_key in seen:
            raise RuntimeError(f"Duplicate NMB determination row key: {row_key}")
        seen.add(row_key)
        disposition, _ = _cell(raw, indexes, "disposition")
        rows.append({
            "row_key": row_key, "source_agency_code": AGENCY_CODE,
            "case_number": primary_case_number,
            "case_cross_references": "; ".join(re.findall(r"\b(?:RD|CR)-\d+\b", case_number, re.I)),
            "canonical_case_type": _canonical_case_type(disposition), "native_case_type": disposition,
            "employer_name": _cell(raw, indexes, "carrier")[0],
            # The listing's Union column is the *applicant* -- the organisation
            # that invoked the Board's services -- not necessarily the union the
            # Board went on to certify.  R-6952 (American Airlines flight
            # dispatchers) lists PAFCA, which lost 99-120 to the incumbent TWU.
            "union_name": _cell(raw, indexes, "union")[0],
            "applicant_union": _cell(raw, indexes, "union")[0],
            "certified_representative": "", "certification_text_snippet": "",
            "representation_asserted": "true" if _is_certification_disposition(disposition) else "false",
            "craft_class": craft_class, "nmb_volume_number": _cell(raw, indexes, "nmbnumber")[0],
            "page_cite": page_cite, "determination_date": determination_date,
            "fiscal_year": fiscal_year,
            "jurisdiction_city": "", "jurisdiction_state": "", "employer_street": "", "employer_zip": "",
            "source_page_url": source_page_url,
            "source_url": urljoin(source_page_url, pdf_href) if pdf_href else source_page_url,
            "scraped_at": scraped_at,
        })
    return rows


def discover_year_page_urls(index_html: str) -> list[str]:
    links = re.findall(r'href=["\']([^"\']+)["\']', index_html, re.I)
    urls = {urljoin(LISTING_URL, href) for href in links if re.search(r"(?:fy)?(?:19|20)\d{2}-determinations/?$", href, re.I)}
    return sorted(urls, key=lambda url: int(_fiscal_year_from_url(url) or 0))


def _read_certification(
    row: dict[str, str],
    *,
    fetch_pdf: Any,
    pdf_to_text: Any,
    delay_seconds: float,
) -> bool:
    """Fill the certified columns from the determination PDF.  Returns read-ok."""
    url = row.get("source_url", "")
    if not url.lower().endswith(".pdf"):
        # 1990s determinations are WordPerfect (.wpd); there is nothing to read.
        logger.warning("NMB %s: no PDF to read (%s)", row["case_number"], url or "no link")
        return False
    text = ""
    for attempt in (1, 2):
        try:
            text = pdf_to_text(fetch_pdf(url, delay_seconds=delay_seconds))
            break
        except Exception as exc:  # transient network / pdftotext failure
            if attempt == 2:
                logger.warning("NMB %s: could not read %s: %s", row["case_number"], url, exc)
                return False
            logger.warning("NMB %s: retrying %s after %s", row["case_number"], url, exc)
    representative, snippet = parse_certification_sentence(text)
    if not representative:
        # Image-only scan, or an unfamiliar certification sentence.  Leave the
        # columns empty -- never fall back to the applicant.
        logger.warning("NMB %s: no certification sentence in %s", row["case_number"], url)
        return True
    row["certified_representative"] = representative
    row["certification_text_snippet"] = snippet
    return True


def scrape_determinations(
    *,
    delay_seconds: float = 0.3,
    fetch_html: Any = None,
    read_documents: bool = True,
    fetch_pdf: Any = None,
    pdf_to_text: Any = None,
) -> list[dict[str, str]]:
    fetcher = fetch_html or fetch_url
    pdf_fetcher = fetch_pdf or fetch_bytes
    text_extractor = pdf_to_text or default_pdf_to_text
    year_urls = discover_year_page_urls(fetcher(LISTING_URL, delay_seconds=delay_seconds))
    if not year_urls:
        raise RuntimeError(f"NMB determination index exposed no year pages: {LISTING_URL}")
    scraped_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows = [row for url in year_urls for row in parse_determinations_table(fetcher(url, delay_seconds=delay_seconds), source_page_url=url, scraped_at=scraped_at)]
    if not rows:
        raise RuntimeError("NMB determination scrape parsed 0 rows")
    if len({row["row_key"] for row in rows}) != len(rows):
        raise RuntimeError("NMB determination scrape produced duplicate row keys")
    certification_rows = [row for row in rows if row["representation_asserted"] == "true"]
    documents_read = 0
    if read_documents:
        for row in certification_rows:
            documents_read += _read_certification(
                row, fetch_pdf=pdf_fetcher, pdf_to_text=text_extractor, delay_seconds=delay_seconds
            )
    parsed = [row for row in certification_rows if row["certified_representative"]]
    differs = [
        row for row in parsed
        if _key_part(row["certified_representative"]) != _key_part(row["applicant_union"])
    ]
    logger.info(
        "NMB determinations: %d rows, %d certification rows, %d documents read, "
        "%d certified representatives parsed, %d where the applicant differs from the certified union",
        len(rows), len(certification_rows), documents_read, len(parsed), len(differs),
    )
    return sorted(rows, key=lambda row: (row["determination_date"], row["row_key"]))


def scrape_to_wide_csv(csv_path: Any, *, delay_seconds: float = 0.3, read_documents: bool = True) -> int:
    return write_wide_csv(
        scrape_determinations(delay_seconds=delay_seconds, read_documents=read_documents),
        csv_path,
        fieldnames=WIDE_FIELDNAMES,
    )
