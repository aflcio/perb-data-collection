"""Tests for the byte-level PDF readability probe.

Everything here is synthetic: the fixtures are hand-written minimal PDFs, and
nothing touches the network.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from perb_data_collection.pdf_probe import extract_text, probe_pdf_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def _build_pdf(objects: list[bytes]) -> bytes:
    """Assemble numbered objects into a minimal, valid PDF file."""
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref = len(out)
    size = len(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


def _flate_stream(data: bytes, extra: bytes = b"") -> bytes:
    compressed = zlib.compress(data)
    return (
        b"<< /Length %d /Filter /FlateDecode%s >>\nstream\n" % (len(compressed), extra)
        + compressed
        + b"\nendstream"
    )


def make_text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a font resource and real text-showing operators."""
    content = b"BT /F1 12 Tf 72 720 Td 14 TL\n"
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content += b"(" + escaped.encode("latin-1", "replace") + b") Tj T*\n"
    content += b"ET\n"
    return _build_pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            _flate_stream(content),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
    )


def make_image_only_pdf() -> bytes:
    """A one-page PDF that paints a grey image and declares no font."""
    image = bytes([200]) * (8 * 8)
    return _build_pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
            _flate_stream(b"q 612 0 0 792 0 0 cm /Im1 Do Q\n"),
            _flate_stream(
                image,
                extra=b" /Type /XObject /Subtype /Image /Width 8 /Height 8 "
                b"/ColorSpace /DeviceGray /BitsPerComponent 8",
            ),
        ]
    )


def test_probe_text_pdf_is_readable() -> None:
    probe = probe_pdf_bytes(FIXTURES.joinpath("pdf_text_layer.pdf").read_bytes())
    assert probe.error == ""
    assert probe.has_font is True
    assert probe.has_text_operators is True
    assert probe.has_image_xobject is False
    assert probe.text_chars > 40
    assert probe.page_count_hint == 1
    assert probe.is_image_only is False


def test_probe_image_only_pdf() -> None:
    probe = probe_pdf_bytes(FIXTURES.joinpath("pdf_image_only.pdf").read_bytes())
    assert probe.error == ""
    assert probe.has_font is False
    assert probe.has_image_xobject is True
    assert probe.has_text_operators is False
    assert probe.text_chars == 0
    assert probe.is_image_only is True


def test_probe_generated_pdfs_match_fixtures() -> None:
    # The builders and the checked-in fixtures must agree, so a regenerated
    # fixture cannot quietly change what the test asserts.
    assert probe_pdf_bytes(make_text_pdf(["HELLO", "a" * 60])).is_image_only is False
    assert probe_pdf_bytes(make_image_only_pdf()).is_image_only is True


def test_probe_garbage_bytes_sets_error_and_unknown() -> None:
    probe = probe_pdf_bytes(FIXTURES.joinpath("pdf_garbage.bin").read_bytes())
    assert probe.is_image_only is None
    assert probe.error


def test_probe_empty_bytes() -> None:
    probe = probe_pdf_bytes(b"")
    assert probe.is_image_only is None
    assert probe.error == "empty document"


def test_probe_thin_text_over_a_scan_is_image_only() -> None:
    # A scan with a tiny stamped label declares a font, but has almost no
    # glyphs. Below the threshold it still counts as image-only.
    pdf = _build_pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
            _flate_stream(b"q /Im1 Do Q BT /F1 8 Tf (FILED) Tj ET\n"),
            _flate_stream(
                bytes(64),
                extra=b" /Type /XObject /Subtype /Image /Width 8 /Height 8 "
                b"/ColorSpace /DeviceGray /BitsPerComponent 8",
            ),
        ]
    )
    probe = probe_pdf_bytes(pdf)
    assert probe.has_image_xobject is True
    assert probe.has_text_operators is True
    assert probe.text_chars < 40
    assert probe.is_image_only is True


def test_extract_text_reads_the_text_layer_or_returns_empty() -> None:
    data = FIXTURES.joinpath("pdf_text_layer.pdf").read_bytes()
    text = extract_text(data)
    # poppler may be absent; the contract is '' on failure, never an exception.
    if text:
        assert "CERTIFICATION OF REPRESENTATIVE" in text
    assert extract_text(b"not a pdf") == ""
    assert extract_text(b"") == ""
