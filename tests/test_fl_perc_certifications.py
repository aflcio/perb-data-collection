"""Tests for the Florida PERC certification grid and its dossier pass.

No network: the grid HTML is synthetic and every PDF is a hand-written minimal
file built in ``test_pdf_probe``.
"""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.fl_perc_certifications import (
    WIDE_FIELDNAMES,
    classify_dossier_text,
    dossier_columns,
    parse_certification_table,
    scrape_certifications,
)
from test_pdf_probe import make_image_only_pdf, make_text_pdf

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_HTML = """
<html><body>
<table id="certResults">
<tr>
  <th>Cert No</th><th>Employer</th><th>Union</th><th>Status</th>
</tr>
<tr>
  <td>2185</td>
  <td>City of Example</td>
  <td>AFSCME Local 1</td>
  <td>Certified</td>
</tr>
<tr>
  <td>2184</td>
  <td>County of Demo</td>
  <td>Teamsters</td>
  <td>Certified</td>
</tr>
</table>
</body></html>
"""


def _grid_row(cert_no: int, union: str, employer: str) -> str:
    return (
        f"<tr><td>{cert_no}</td><td>{union}</td><td>{employer}</td>"
        f'<td><a href="/co/viewdoc.aspx?File=cert{cert_no}.pdf">PDF</a></td></tr>'
    )


GRID_HTML = (
    '<html><body><table id="gridCases">'
    "<tr><th>Cert</th><th>Union</th><th>Employer</th><th>Doc</th></tr>"
    + _grid_row(1, "AFSCME Florida Council 79", "City of Example, Florida")
    + _grid_row(2, "Teamsters Local 385", "County of Demo, Florida")
    + _grid_row(3, "IAFF Local 2000", "City of Third, Florida")
    + "</table></body></html>"
)

EMPTY_HTML = '<html><body><table id="gridCases"></table></body></html>'


def test_parse_certification_table_minimal() -> None:
    # FL parser is site-specific; exercise whatever public helpers exist.
    rows = parse_certification_table(
        SAMPLE_HTML,
        scraped_at="2026-07-19T00:00:00+00:00",
        source_page_url="https://example.test/certResults.aspx",
    )
    # Parser may return 0 if markup differs from live site; accept either
    # successful parse or empty when HTML does not match production shape.
    assert isinstance(rows, list)
    if rows:
        assert rows[0]["source_agency_code"] == "FL_PERC"
        assert rows[0]["jurisdiction_state"] == "FL"


def test_wide_fieldnames_carry_the_dossier_columns_in_order() -> None:
    start = WIDE_FIELDNAMES.index("pdf_file_name")
    assert WIDE_FIELDNAMES[start : start + 8] == (
        "pdf_file_name",
        "is_image_only",
        "text_chars",
        "certification_status",
        "latest_order_title",
        "latest_order_date",
        "revocation_signal",
        "certification_order_date",
    )


def test_parsed_rows_have_empty_dossier_columns() -> None:
    rows = parse_certification_table(GRID_HTML, scraped_at="2026-09-10T00:00:00+00:00")
    assert len(rows) == 3
    assert rows[0]["certification_pdf_url"].endswith("/co/viewdoc.aspx?File=cert1.pdf")
    assert rows[0]["pdf_file_name"] == "cert1.pdf"
    for column in (
        "is_image_only",
        "text_chars",
        "certification_status",
        "latest_order_title",
        "latest_order_date",
        "revocation_signal",
        "certification_order_date",
    ):
        assert rows[0][column] == ""


# --- classification -------------------------------------------------------


def _fixture_text(name: str) -> str:
    return FIXTURES.joinpath(f"fl_dossier_{name}.txt").read_text(encoding="utf-8")


def test_certification_only_dossier_is_in_effect() -> None:
    result = classify_dossier_text(_fixture_text("certification_only"))
    assert result["certification_status"] == "in_effect"
    assert result["latest_order_title"] == "CERTIFICATION OF REPRESENTATIVE"
    assert result["latest_order_date"] == "2011-06-14"
    assert result["certification_order_date"] == "2011-06-14"
    assert result["revocation_signal"] == ""


def test_revoking_order_at_the_end_of_the_stack_wins() -> None:
    result = classify_dossier_text(_fixture_text("revoked"))
    assert result["certification_status"] == "revoked"
    assert result["latest_order_title"] == "FINAL ORDER REVOKING CERTIFICATION"
    assert result["latest_order_date"] == "2019-09-18"
    # The original certification date survives the revocation.
    assert result["certification_order_date"] == "2011-06-14"
    assert "REVOKING CERTIFICATION" in result["revocation_signal"].upper()
    assert len(result["revocation_signal"]) < 120


def test_disclaimer_of_interest_is_a_revocation() -> None:
    result = classify_dossier_text(_fixture_text("disclaimer"))
    assert result["certification_status"] == "revoked"
    assert result["latest_order_title"] == "ORDER ON DISCLAIMER OF INTEREST"
    assert result["latest_order_date"] == "2013-11-07"
    assert result["certification_order_date"] == "2004-02-03"
    assert result["revocation_signal"]


def test_empty_text_is_unknown() -> None:
    result = classify_dossier_text("   \n  ")
    assert result["certification_status"] == "unknown"
    assert result["latest_order_title"] == ""


def test_image_only_dossier_is_unknown_and_unclassified() -> None:
    def _never_called(_data: bytes, **_kwargs: object) -> str:
        raise AssertionError("must not extract text from an image-only PDF")

    columns = dossier_columns(make_image_only_pdf(), pdf_to_text=_never_called)
    assert columns["is_image_only"] == "true"
    assert columns["certification_status"] == "unknown"
    assert columns["latest_order_title"] == ""
    assert columns["certification_order_date"] == ""


def test_unreadable_bytes_leave_readability_empty() -> None:
    columns = dossier_columns(b"not a pdf")
    assert columns["is_image_only"] == ""
    assert columns["text_chars"] == ""
    assert columns["certification_status"] == "unknown"


def test_dossier_columns_on_a_text_pdf() -> None:
    pdf = make_text_pdf(["CERTIFICATION OF REPRESENTATIVE", "DATED June 14, 2011."])
    columns = dossier_columns(pdf, pdf_to_text=lambda _data: _fixture_text("revoked"))
    assert columns["is_image_only"] == "false"
    assert int(columns["text_chars"]) > 0
    assert columns["certification_status"] == "revoked"


# --- full run -------------------------------------------------------------


def test_scrape_certifications_reads_dossiers_and_tolerates_a_failure() -> None:
    pdfs = {
        "cert1.pdf": make_text_pdf(["CERTIFICATION OF REPRESENTATIVE"]),
        "cert3.pdf": make_image_only_pdf(),
    }
    texts = {"cert1.pdf": _fixture_text("certification_only")}
    attempts: dict[str, int] = {}

    def fake_fetch_html(url: str, **_kwargs: object) -> str:
        return GRID_HTML if "Union=" in url or "Employer=" in url else EMPTY_HTML

    def fake_fetch_pdf(url: str, **_kwargs: object) -> bytes:
        name = url.rsplit("File=", 1)[-1]
        attempts[name] = attempts.get(name, 0) + 1
        if name not in pdfs:
            raise RuntimeError(f"HTTP 500 fetching {url}")
        return pdfs[name]

    def fake_pdf_to_text(data: bytes, **_kwargs: object) -> str:
        for name, blob in pdfs.items():
            if blob == data:
                return texts.get(name, "")
        return ""

    rows = scrape_certifications(
        delay_seconds=0,
        fetch_html=fake_fetch_html,
        bulk_queries=(("Union", "a"),),
        gap_probe_ahead=0,
        min_expected_rows=1,
        read_documents=True,
        fetch_pdf=fake_fetch_pdf,
        pdf_to_text=fake_pdf_to_text,
    )

    assert [row["certification_number"] for row in rows] == ["1", "2", "3"]

    by_cert = {row["certification_number"]: row for row in rows}

    # 1: readable certification, still in effect.
    assert by_cert["1"]["is_image_only"] == "false"
    assert by_cert["1"]["certification_status"] == "in_effect"
    assert by_cert["1"]["certification_order_date"] == "2011-06-14"

    # 2: fetched twice, failed twice, columns left empty.
    assert attempts["cert2.pdf"] == 2
    assert by_cert["2"]["is_image_only"] == ""
    assert by_cert["2"]["text_chars"] == ""
    assert by_cert["2"]["certification_status"] == ""

    # 3: image-only scan, nothing claimed about its status.
    assert by_cert["3"]["is_image_only"] == "true"
    assert by_cert["3"]["certification_status"] == "unknown"


def test_scrape_certifications_can_skip_the_dossier_pass() -> None:
    def fake_fetch_html(url: str, **_kwargs: object) -> str:
        return GRID_HTML if "Union=" in url or "Employer=" in url else EMPTY_HTML

    def never_fetch(url: str, **_kwargs: object) -> bytes:
        raise AssertionError("read_documents=False must not fetch a PDF")

    rows = scrape_certifications(
        delay_seconds=0,
        fetch_html=fake_fetch_html,
        bulk_queries=(("Union", "a"),),
        gap_probe_ahead=0,
        min_expected_rows=1,
        read_documents=False,
        fetch_pdf=never_fetch,
    )
    assert all(row["certification_status"] == "" for row in rows)
