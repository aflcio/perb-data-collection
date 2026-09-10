"""Tests for DC PERB certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.dc_perb_certifications import (
    _parse_order_date,
    parse_certification_table,
    scrape_certifications,
)

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
    assert order_date_source == "body"


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
        assert row["order_date_source"] == "body"

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
