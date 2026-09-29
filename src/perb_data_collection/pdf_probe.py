"""Byte-level readability probe for PDFs, plus a text extraction helper.

WHY THIS EXISTS
---------------
Collectors that land a "is this document machine readable" flag used to guess
from the file name (``*_scan.pdf``, ``IMG_*.pdf`` and friends). On the Florida
PERC certification dossiers that guess was wrong in both directions on roughly a
third of the rows: text-layer PDFs named like scans, and scanned images named
like ordinary orders.

The only honest test reads the file. A PDF carries a text layer when it declares
at least one font resource (``/Font``) and its content streams contain
text-showing operators (``Tj``, ``TJ``, ``'``, ``"``). A scan carries an image
XObject (``/Subtype /Image``) and no fonts. Content streams are usually
``FlateDecode`` compressed, so they are inflated with zlib before the operator
scan.

Nothing here needs a PDF library, and nothing here touches the network.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from html import unescape as html_unescape
from pathlib import Path

# A file with a font and a couple of stray operators but almost no glyphs is a
# cover page over a scan, not a readable document.
MIN_TEXT_CHARS = 40

_STREAM_RE = re.compile(rb"stream\r?\n?(.*?)endstream", re.S)
_FONT_RE = re.compile(rb"/Font\b")
_IMAGE_XOBJECT_RE = re.compile(rb"/Subtype\s*/Image\b")
_PAGE_RE = re.compile(rb"/Type\s*/Page\b(?!s)")
_COUNT_RE = re.compile(rb"/Count\s+(\d+)")

# Text-showing operators. Tj / TJ take an operand; ' and " are the newline
# forms. Each must be preceded by an operand and followed by a delimiter so a
# stray "TJ" inside a name or a word does not count.
_TEXT_OP_RE = re.compile(rb"(?:\)|\]|\d)\s*(?:Tj|TJ|'|\")(?![A-Za-z0-9])")

# Text drawn inside a content stream: literal strings between BT/ET.
_BT_ET_RE = re.compile(rb"BT\b(.*?)\bET\b", re.S)
_LITERAL_STRING_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)", re.S)
_HEX_STRING_RE = re.compile(rb"<([0-9A-Fa-f\s]+)>")


@dataclass(frozen=True)
class PdfProbe:
    """What a byte-level read can honestly say about one PDF."""

    has_font: bool = False
    has_image_xobject: bool = False
    has_text_operators: bool = False
    text_chars: int = 0
    page_count_hint: int = 0
    is_image_only: bool | None = None
    error: str = ""


def _inflate_streams(data: bytes) -> list[bytes]:
    """Return every content stream, inflated when it is FlateDecode."""
    out: list[bytes] = []
    for match in _STREAM_RE.finditer(data):
        raw = match.group(1)
        try:
            out.append(zlib.decompress(raw))
            continue
        except zlib.error:
            pass
        # Some producers pad the stream; try a tolerant inflate before giving up.
        try:
            out.append(zlib.decompressobj().decompress(raw))
            continue
        except zlib.error:
            pass
        out.append(raw)
    return out


def _count_stream_text(stream: bytes) -> int:
    """Approximate glyph count drawn by the text-showing operators in a stream."""
    total = 0
    for block in _BT_ET_RE.findall(stream) or ([stream] if _TEXT_OP_RE.search(stream) else []):
        for literal in _LITERAL_STRING_RE.findall(block):
            total += len(re.sub(rb"\\.", b"x", literal))
        for hexed in _HEX_STRING_RE.findall(block):
            total += len(re.sub(rb"\s", b"", hexed)) // 2
    return total


def probe_pdf_bytes(data: bytes) -> PdfProbe:
    """Decide whether ``data`` is a text-layer PDF or an image-only scan.

    Returns a probe with ``error`` set and ``is_image_only=None`` when the bytes
    are not a PDF or cannot be read at all. Never raises.
    """
    if not data:
        return PdfProbe(error="empty document", is_image_only=None)
    try:
        head = data[:1024]
        if b"%PDF-" not in head:
            return PdfProbe(error="missing %PDF- header", is_image_only=None)

        has_font = bool(_FONT_RE.search(data))
        has_image = bool(_IMAGE_XOBJECT_RE.search(data))

        streams = _inflate_streams(data)
        has_text_ops = False
        text_chars = 0
        for stream in streams:
            if _TEXT_OP_RE.search(stream):
                has_text_ops = True
                text_chars += _count_stream_text(stream)

        page_count = len(_PAGE_RE.findall(data))
        if not page_count:
            counts = _COUNT_RE.findall(data)
            page_count = max((int(c) for c in counts), default=0)

        readable_text = has_text_ops and text_chars >= MIN_TEXT_CHARS
        is_image_only = has_image and not has_font and not readable_text

        return PdfProbe(
            has_font=has_font,
            has_image_xobject=has_image,
            has_text_operators=has_text_ops,
            text_chars=text_chars,
            page_count_hint=page_count,
            is_image_only=is_image_only,
        )
    except Exception as exc:  # noqa: BLE001 - a malformed PDF must not stop a run
        return PdfProbe(error=f"{type(exc).__name__}: {exc}", is_image_only=None)


def extract_text(data: bytes, *, first_pages: int | None = None, layout: bool = True) -> str:
    """Extract the text layer with poppler ``pdftotext`` (``-layout`` by default).

    Returns '' on any failure, including poppler not being installed, so a
    caller can treat "no text" and "could not read" the same way.

    ``layout=False`` keeps reading order, which is what a caption parser wants:
    ``-layout`` interleaves a caption's ``)`` column and the case-number column
    into the party names.
    """
    if not data:
        return ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "doc.pdf"
            txt_path = Path(tmp) / "doc.txt"
            pdf_path.write_bytes(data)
            cmd = ["pdftotext"] + (["-layout"] if layout else [])
            if first_pages is not None and first_pages > 0:
                cmd.extend(["-f", "1", "-l", str(first_pages)])
            cmd.extend([str(pdf_path), str(txt_path)])
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            return txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - extraction is best effort
        return ""


# --- whole-document text, with OCR for scans --------------------------------
#
# A scanned order downloads perfectly and has no text layer, so "no text" from
# pdftotext is not "no order". DC PERB's 12-RC-02 certification (No. 165) is a
# three-page scan whose text layer holds only the e-filing stamp; the operative
# "IT IS HEREBY CERTIFIED" section, which names a different union from the
# petitioner, is on page 2 and is only readable by OCR.

TEXT_METHOD_TEXT_LAYER = "text_layer"
TEXT_METHOD_DOCX = "docx"
TEXT_METHOD_OCR = "ocr"
TEXT_METHOD_OCR_UNAVAILABLE = "ocr_unavailable"
TEXT_METHOD_UNREADABLE = "unreadable"


def ocr_pdf(data: bytes, *, first_page: int = 1, last_page: int | None = None, dpi: int = 200) -> str | None:
    """OCR PDF pages with poppler ``pdftoppm`` + ``tesseract``.

    Returns ``None`` (not '') when either tool is missing, so a caller can tell
    "OCR found nothing" from "OCR was not possible here".
    """
    if not data:
        return ""
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "doc.pdf"
            pdf_path.write_bytes(data)
            cmd = ["pdftoppm", "-r", str(dpi), "-png", "-f", str(first_page)]
            if last_page is not None:
                cmd.extend(["-l", str(last_page)])
            cmd.extend([str(pdf_path), str(Path(tmp) / "page")])
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            pages: list[str] = []
            for image in sorted(Path(tmp).glob("page-*.png")):
                done = subprocess.run(
                    ["tesseract", str(image), "stdout"],
                    check=True,
                    capture_output=True,
                    timeout=180,
                )
                pages.append(done.stdout.decode("utf-8", errors="replace"))
            return "\f".join(pages)
    except Exception:  # noqa: BLE001 - OCR is best effort
        return ""


def docx_text(data: bytes) -> str:
    """Paragraph text of a .docx (DC PERB serves some certifications as Word)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br/>", "\n", xml)
    return html_unescape(re.sub(r"<[^>]+>", "", xml))


def looks_space_starved(text: str) -> bool:
    """True when a text layer has lost its word spaces.

    Old scanner software wrote text layers like "TheAmericanFederationof
    State,countyandMunicipalEmployees". A name read from that matches nothing,
    so such a layer is re-read by OCR.
    """
    words = re.findall(r"[A-Za-z]{2,}", text or "")
    if len(words) < 30:
        return False
    long_words = sum(1 for word in words if len(word) >= 18)
    return long_words / len(words) > 0.03


def document_text(
    data: bytes,
    *,
    layout: bool = False,
    ocr_last_page: int | None = 8,
) -> tuple[str, str]:
    """Return ``(text, method)`` for a PDF or .docx, OCR'ing a scan.

    ``method`` is one of ``text_layer``, ``docx``, ``ocr``, ``ocr_unavailable``
    or ``unreadable``, so a null downstream can be attributed: a scan on a host
    without tesseract is not the same finding as a document that says nothing.
    """
    if not data:
        return "", TEXT_METHOD_UNREADABLE
    if data[:2] == b"PK":
        text = docx_text(data)
        return text, TEXT_METHOD_DOCX if text.strip() else TEXT_METHOD_UNREADABLE
    if b"%PDF-" not in data[:1024]:
        return "", TEXT_METHOD_UNREADABLE
    text = extract_text(data, layout=layout)
    if len(re.sub(r"\s+", "", text)) >= 200 and not looks_space_starved(text):
        return text, TEXT_METHOD_TEXT_LAYER
    ocr = ocr_pdf(data, last_page=ocr_last_page)
    if text.strip() and (not ocr or looks_space_starved(ocr)):
        # A starved text layer still beats no OCR, or OCR that is no better.
        return text, TEXT_METHOD_TEXT_LAYER
    if ocr is None:
        return text, TEXT_METHOD_OCR_UNAVAILABLE
    if ocr.strip():
        return ocr, TEXT_METHOD_OCR
    return text, TEXT_METHOD_UNREADABLE
