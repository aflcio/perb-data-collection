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

import re
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
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


def extract_text(data: bytes, *, first_pages: int | None = None) -> str:
    """Extract the text layer with poppler ``pdftotext -layout``.

    Returns '' on any failure, including poppler not being installed, so a
    caller can treat "no text" and "could not read" the same way.
    """
    if not data:
        return ""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "doc.pdf"
            txt_path = Path(tmp) / "doc.txt"
            pdf_path.write_bytes(data)
            cmd = ["pdftotext", "-layout"]
            if first_pages is not None and first_pages > 0:
                cmd.extend(["-f", "1", "-l", str(first_pages)])
            cmd.extend([str(pdf_path), str(txt_path)])
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            return txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - extraction is best effort
        return ""
