"""Tests for DC PERB certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.dc_perb_certifications import (
    CERTIFIED,
    SECTION_NOT_FOUND,
    _parse_order_date,
    apply_document,
    parse_caption_roles,
    parse_certification_table,
    parse_certified_representative,
    scrape_certifications,
)
from perb_data_collection.pdf_probe import document_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_certification_table_fixture() -> None:
    html = (FIXTURES / "dc_perb_certifications_page.html").read_text()
    rows = parse_certification_table(html, scraped_at="2026-07-14T00:00:00+00:00")
    assert len(rows) >= 5
    sample = rows[0]
    assert sample["source_agency_code"] == "DC_PERB"
    assert sample["jurisdiction_city"] == "Washington"
    assert sample["jurisdiction_state"] == "DC"
    assert sample["employer_name"]
    assert sample["row_key"].startswith("DC_PERB:")
    assert sample["row_key"].count(":") >= 3
    assert len({r["row_key"] for r in rows}) == len(rows)
    assert sample["canonical_case_type"] in {
        "RECOGNITION",
        "AMENDMENT_OF_CERTIFICATION",
        "DECERTIFICATION",
        "UNIT_CLARIFICATION",
        "UNIT_MODIFICATION",
        "ULP",
        "CERTIFICATION",
    }


def test_scrape_certifications_uses_fixture() -> None:
    html = (FIXTURES / "dc_perb_certifications_page.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    rows = scrape_certifications(fetch_html=fake_fetch, read_documents=False)
    assert len(rows) >= 5
    # No document read requested: order_date columns stay untouched/empty.
    assert all(row["order_date"] == "" for row in rows)


def test_parse_certification_table_removes_employer_list_punctuation() -> None:
    html = (FIXTURES / "dc_perb_certifications_page.html").read_text()
    html = html.replace(
        "District of Columbia Department of Aging and Community Living</td>",
        "District of Columbia Department of Aging and Community Living,</td>",
        1,
    )

    rows = parse_certification_table(html, scraped_at="2026-07-14T00:00:00+00:00")

    assert rows[0]["employer_name"] == (
        "District of Columbia Department of Aging and Community Living"
    )


def test_parse_order_date_prefers_body_date_over_stamp() -> None:
    # Sampled from a real DC PERB certification PDF (pdftotext -l 2 -layout):
    # the e-filing stamp near the top postdates the order body's signature
    # date by over a week, so the body date is the one that belongs in the
    # warehouse.
    text = (
        "                                                                          RECEIVED\n"
        "                                                                          Jul 25 2025 07:46PM EDT\n"
        "CERTIFICATION OF REPRESENTATIVE\n"
        "BY ORDER OF THE PUBLIC EMPLOYEE RELATIONS BOARD\n"
        "\n"
        "July 17, 2025\n"
        "\n"
        "Washington, D.C.\n"
    )
    order_date, order_date_raw, order_date_source = _parse_order_date(text)
    assert order_date == "2025-07-17"
    assert order_date_raw == "July 17, 2025"
    # The date sits in the "BY ORDER OF THE ... BOARD" closing block.
    assert order_date_source == "order_block"


def test_parse_order_date_falls_back_to_stamp_when_no_body_date() -> None:
    text = (
        "                                                                          RECEIVED\n"
        "                                                                          Jul 25 2025 07:46PM EDT\n"
        "CERTIFICATION OF REPRESENTATIVE\n"
        "No written-out date appears anywhere in this order.\n"
    )
    order_date, order_date_raw, order_date_source = _parse_order_date(text)
    assert order_date == "2025-07-25"
    assert order_date_raw == "Jul 25 2025 07:46PM EDT"
    assert order_date_source == "stamp"


def test_parse_order_date_empty_when_no_date_present() -> None:
    text = "CERTIFICATION OF REPRESENTATIVE\nNo date anywhere in this text.\n"
    order_date, order_date_raw, order_date_source = _parse_order_date(text)
    assert order_date == ""
    assert order_date_raw == ""
    assert order_date_source == ""


def test_scrape_certifications_reads_documents_with_fake_fetcher() -> None:
    html = (FIXTURES / "dc_perb_certifications_page.html").read_text()

    def fake_fetch_html(url: str, **kwargs: object) -> str:
        return html

    body_text = (
        "CERTIFICATION OF REPRESENTATIVE\n"
        "BY ORDER OF THE PUBLIC EMPLOYEE RELATIONS BOARD\n"
        "August 3, 2025\n"
        "Washington, D.C.\n"
    )
    stamp_only_text = (
        "RECEIVED\nJul 25 2025 07:46PM EDT\nCERTIFICATION OF REPRESENTATIVE\n"
    )

    call_count = {"n": 0}

    def fake_fetch_pdf(url: str, **kwargs: object) -> bytes:
        call_count["n"] += 1
        if "E0E3CD0A" in url:
            raise RuntimeError("simulated transient failure fetching PDF")
        return b"pdf-bytes-for-" + url.encode()

    def fake_pdf_to_text(pdf_bytes: bytes) -> str:
        raw = pdf_bytes.decode()
        if "186BBA64" in raw:
            return body_text
        return stamp_only_text

    rows = scrape_certifications(
        fetch_html=fake_fetch_html,
        read_documents=True,
        fetch_pdf=fake_fetch_pdf,
        pdf_to_text=fake_pdf_to_text,
        delay_seconds=0,
    )

    assert len(rows) >= 5

    # The row whose document raises on every attempt (retried once, still
    # fails) leaves its date columns blank rather than crashing the scrape.
    failing_rows = [r for r in rows if "E0E3CD0A" in r["document_url"]]
    assert failing_rows
    for row in failing_rows:
        assert row["order_date"] == ""
        assert row["order_date_raw"] == ""
        assert row["order_date_source"] == ""

    # The row whose fake document text carries a written-out body date.
    body_rows = [r for r in rows if "186BBA64" in r["document_url"]]
    assert body_rows
    for row in body_rows:
        assert row["order_date"] == "2025-08-03"
        # The date follows the "BY ORDER OF THE ... BOARD" closing block.
        assert row["order_date_source"] == "order_block"
        assert row["order_date_precision"] == "day"

    # Every remaining row got a stamp-sourced date from the fake extractor.
    other_rows = [
        r
        for r in rows
        if "E0E3CD0A" not in r["document_url"] and "186BBA64" not in r["document_url"]
    ]
    assert other_rows
    for row in other_rows:
        assert row["order_date"] == "2025-07-25"
        assert row["order_date_source"] == "stamp"

    # The failing document was retried once (two attempts) per occurrence.
    assert call_count["n"] >= 2 * len(failing_rows)


# --- the certification document decides the union (12-RC-02 and friends) ---
#
# Fixtures are the real documents: OCR text of the scanned certifications
# (tesseract over pdftoppm at 200 dpi), the text layer of digital ones, and one
# .docx as DC serves it.


def _live_row(case_number: str, certification_number: str) -> dict[str, str]:
    html = (FIXTURES / "dc_perb_certifications_live_2026-09-10.html").read_text()
    rows = parse_certification_table(html, scraped_at="2026-09-29T00:00:00+00:00")
    return next(
        r for r in rows
        if r["case_number"] == case_number and r["certification_number"] == certification_number
    )


def test_listing_strips_the_trailing_vs_and_keeps_the_raw_cells() -> None:
    row = _live_row("12-RC-02", "165")
    assert row["listing_complainant"] == "International Union of Public Employees"
    assert row["listing_respondent"].endswith("National Association of Government Employees, Local R3-07")
    # Two unions in the listing: which one represents the unit is the
    # certification's outcome, so the listing alone names no union.
    assert row["union_name"] == ""
    assert row["employer_name"] == "District of Columbia Office of Unified Communications"


def test_12_rc_02_certifies_nage_not_the_petitioner() -> None:
    text = (FIXTURES / "dc_perb_12-rc-02_cert165_ocr.txt").read_text()
    out = apply_document(_live_row("12-RC-02", "165"), text, "ocr")
    assert out["petitioner"] == "International Union of Public Employees"
    assert out["agency"] == "District of Columbia Office of Unified Communications"
    assert out["intervenor"] == "National Association of Government Employees, Local R3-07"
    assert out["certified_representative"] == (
        "National Association of Government Employees, Local R3-07"
    )
    assert out["certification_result"] == CERTIFIED
    assert out["union_name"] == out["certified_representative"]
    assert out["union_name_source"] == "certification"
    assert out["employer_name"] == "District of Columbia Office of Unified Communications"
    assert out["order_date"] == "2018-12-05"
    assert out["order_date_source"] == "order_block"


def test_contested_certification_that_cannot_be_read_names_no_union() -> None:
    # 81-RC-05: FOP petitioned, IBPO Local 442 intervened, FOP won. The scan's
    # right edge is cropped, so OCR loses the winner's name. The listing's
    # one-union guess used to pick the intervenor; now nothing is claimed.
    text = (FIXTURES / "dc_perb_81-rc-05_cert10_ocr.txt").read_text()
    out = apply_document(_live_row("81-RC-05", "10"), text, "ocr")
    assert out["certified_representative"] == ""
    assert out["certification_result"] == SECTION_NOT_FOUND
    assert "Local 442" not in out["union_name"]


def test_parenthetical_acronym_survives_caption_cleanup() -> None:
    text = (FIXTURES / "dc_perb_96-rc-03_cert94.txt").read_text()
    name, result = parse_certified_representative(text)
    assert result == CERTIFIED
    assert name.endswith("AFL-CIO (IBPO)")
    roles = parse_caption_roles(text)
    assert roles["petitioner"] == "District of Columbia Protective Services Association"
    assert roles["agency"] == "District of Columbia Department of Administrative Services"


def test_decertification_petition_by_individuals_keeps_the_incumbent() -> None:
    text = (FIXTURES / "dc_perb_95-rd-01_cert92.txt").read_text()
    out = apply_document(_live_row("95-RD-01", "92"), text, "text_layer")
    assert out["certified_representative"] == "International Association of Firefighters, Local 36"
    assert out["respondent"] == "International Association of Firefighters, Local 36"
    assert out["employer_name"] == "D.C. Fire and Emergency Medical Services Department"
    assert out["petitioner"].startswith("Vaughn L. Bennett")


def test_docx_certification_is_read() -> None:
    text, method = document_text((FIXTURES / "dc_perb_24-rc-01_cert174.docx").read_bytes())
    assert method == "docx"
    name, result = parse_certified_representative(text)
    assert (name, result) == ("American Federation of Government Employees Local 631", CERTIFIED)
    assert _parse_order_date(text)[0] == "2024-10-17"


def test_no_representative_certification_names_no_union() -> None:
    text = (
        "In the Matter of:\nSome Union Local 1\nPetitioner\nand\nD.C. Department of Parks\nAgency\n"
        "CERTIFICATION OF RESULTS\nIT IS HEREBY CERTIFIED THAT: no labor organization has "
        "been selected by a majority of the valid ballots cast.\n"
    )
    out = apply_document(_live_row("12-RC-02", "165"), text, "text_layer")
    assert out["certification_result"] == "no_representative"
    assert out["union_name"] == ""
    assert out["union_name_source"] == "no_representative"
