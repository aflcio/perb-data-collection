"""Optional poppler pdftotext wrapper used by PDF-layout collectors."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def pdf_bytes_to_text(pdf_bytes: bytes, *, layout: bool = True) -> str:
    """Run poppler ``pdftotext`` on in-memory PDF bytes. Requires pdftotext on PATH."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "doc.pdf"
        txt_path = Path(tmp) / "doc.txt"
        pdf_path.write_bytes(pdf_bytes)
        cmd = ["pdftotext"]
        if layout:
            cmd.append("-layout")
        cmd.extend([str(pdf_path), str(txt_path)])
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "pdftotext not found on PATH. Install poppler-utils to use PDF collectors."
            ) from exc
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"pdftotext failed: {err}") from exc
        return txt_path.read_text(encoding="utf-8", errors="replace")
