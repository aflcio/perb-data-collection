from pathlib import Path

from perb_data_collection.collectors.nmb_representation_determinations import (
    LISTING_URL,
    WIDE_FIELDNAMES,
    _is_certification_disposition,
    _read_certification,
    discover_year_page_urls,
    parse_certification_sentence,
    parse_determinations_table,
    scrape_determinations,
)


def test_discovers_calendar_and_fiscal_year_pages() -> None:
    html = '<a href="2019-determinations/">2019</a><a href="fy2026-determinations/">FY26</a><a href="about/">About</a>'
    assert discover_year_page_urls(html) == [f"{LISTING_URL}2019-determinations/", f"{LISTING_URL}fy2026-determinations/"]


def test_parses_header_drift_and_multi_craft_case() -> None:
    html = '''<table><tr><th>Page Cite</th><th>Date</th><th>Case</th><th>Carrier</th><th>Union</th><th>Craft/Class</th><th>Disposition</th><th>53 NMB Number</th></tr>
    <tr><td><a href="/docs/r7634.pdf">R-7634</a></td><td>10/02/24</td><td>R-7634 (NMB File No. CR-7253)</td><td>TGS Cedar Port Railroad, LLC</td><td>BLET</td><td>Train and Engine Service Employees</td><td>Certification</td><td>53 NMB 12</td></tr>
    <tr><td>R-7634</td><td>10/02/24</td><td>R-7634</td><td>TGS Cedar Port Railroad, LLC</td><td>BLET</td><td>Dispatchers</td><td>Dismissal</td><td>53 NMB 13</td></tr></table>'''
    rows = parse_determinations_table(html, source_page_url=f"{LISTING_URL}fy2026-determinations/", scraped_at="2026-09-03T00:00:00+00:00")
    assert len(rows) == 2
    assert rows[0]["case_cross_references"] == "CR-7253"
    assert rows[0]["canonical_case_type"] == "CERTIFICATION"
    assert rows[0]["source_url"] == "https://nmb.gov/docs/r7634.pdf"
    assert rows[1]["canonical_case_type"] == ""
    assert rows[1]["fiscal_year"] == "2026"


FY2025_FIXTURE = Path(__file__).parent / "fixtures" / "nmb_fy2025_determinations.html"
R6952_TEXT_FIXTURE = Path(__file__).parent / "fixtures" / "nmb_r6952_certification.txt"
FY2025_URL = f"{LISTING_URL}fy2025-determinations/"


def _fy2025_rows() -> list[dict[str, str]]:
    return parse_determinations_table(
        FY2025_FIXTURE.read_text(encoding="utf-8"),
        source_page_url=FY2025_URL,
        scraped_at="2026-09-10T00:00:00+00:00",
    )


def test_fy2025_fixture_parses_with_representation_columns() -> None:
    rows = _fy2025_rows()
    assert rows
    for column in (
        "applicant_union",
        "certified_representative",
        "certification_text_snippet",
        "representation_asserted",
    ):
        assert column in WIDE_FIELDNAMES
        assert column in rows[0]
    certification = next(row for row in rows if row["case_number"] == "R-7634")
    assert certification["applicant_union"] == certification["union_name"] == "BLET"
    assert certification["representation_asserted"] == "true"
    assert certification["canonical_case_type"] == "CERTIFICATION"
    # FY2024+ pages hang the PDF off the volume-number cell, not Page Cite.
    assert certification["source_url"].endswith("24.10.02-R-7634-Certification.pdf")
    # Nothing is asserted until the determination itself has been read.
    assert certification["certified_representative"] == ""


def test_dispositions_that_are_not_certifications_assert_nothing() -> None:
    dismissal = next(row for row in _fy2025_rows() if row["native_case_type"] == "Dismissal")
    assert dismissal["representation_asserted"] == "false"
    assert dismissal["canonical_case_type"] == ""
    assert dismissal["certified_representative"] == ""
    assert dismissal["certification_text_snippet"] == ""


def test_disposition_classification_covers_the_measured_inventory() -> None:
    for certification in (
        "Certification",
        "Certification – TWU",
        "FUI – certification",
        "Findings Upon Investigation – Certification Determination",
        "Investigation- Certification Determination",
    ):
        assert _is_certification_disposition(certification), certification
    for other in (
        "Dismissal",
        "Dismissal – Withdrawn During Investigation",
        "Transfer of Certification",
        "Certification transferred",
        "Cert-revoked",
        "Revocation of Certification",
        "Jurisdictional Opinion",
        "Appeal Denied",
        "",
    ):
        assert not _is_certification_disposition(other), other


def test_certification_sentence_parses_across_line_wraps() -> None:
    text = """                         CERTIFICATION

      NOW, THEREFORE, in accordance with Section 2, Ninth,
of the RLA, as amended, and based upon its investigation
pursuant thereto, the Board certifies that the Transport
Workers Union of America has been duly designated and
authorized to represent for the purposes of the RLA, as
amended, the craft or class of Flight Dispatchers.
"""
    representative, snippet = parse_certification_sentence(text)
    assert representative == "Transport Workers Union of America"
    assert "duly designated and authorized to represent" in snippet
    assert len(snippet) <= 300


def test_real_r6952_text_names_the_incumbent_not_the_applicant() -> None:
    representative, _snippet = parse_certification_sentence(
        R6952_TEXT_FIXTURE.read_text(encoding="utf-8")
    )
    assert representative == "Transport Workers Union of America"
    assert "PAFCA" not in representative


def test_missing_sentence_and_failed_fetch_leave_the_columns_empty() -> None:
    assert parse_certification_sentence("Nothing here about representation.") == ("", "")

    row = {
        "case_number": "R-7634",
        "source_url": "https://nmb.gov/x.pdf",
        "certified_representative": "",
        "certification_text_snippet": "",
    }

    def boom(url: str, **kwargs: object) -> bytes:
        raise RuntimeError("connection reset")

    assert (
        _read_certification(row, fetch_pdf=boom, pdf_to_text=lambda raw: "", delay_seconds=0)
        is False
    )
    assert row["certified_representative"] == ""
    assert row["certification_text_snippet"] == ""


def test_scrape_retries_once_and_never_copies_the_applicant() -> None:
    attempts: list[str] = []

    def flaky(url: str, **kwargs: object) -> bytes:
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError("transient")
        return b"%PDF"

    row = {
        "case_number": "R-6952",
        "source_url": "https://nmb.gov/31n015.pdf",
        "applicant_union": "PAFCA",
        "certified_representative": "",
        "certification_text_snippet": "",
    }
    text = R6952_TEXT_FIXTURE.read_text(encoding="utf-8")
    assert _read_certification(row, fetch_pdf=flaky, pdf_to_text=lambda raw: text, delay_seconds=0)
    assert len(attempts) == 2
    assert row["certified_representative"] == "Transport Workers Union of America"


def test_scrape_determinations_uses_injected_doubles() -> None:
    fy2025_html = FY2025_FIXTURE.read_text(encoding="utf-8")

    def fetch_html(url: str, **kwargs: object) -> str:
        if url == LISTING_URL:
            return '<a href="fy2025-determinations/">FY2025</a>'
        return fy2025_html

    rows = scrape_determinations(
        delay_seconds=0,
        fetch_html=fetch_html,
        fetch_pdf=lambda url, **kwargs: b"%PDF",
        pdf_to_text=lambda raw: (
            "the Board certifies that Brotherhood of Locomotive Engineers and Trainmen "
            "has been duly designated and authorized to represent for the purposes of the RLA"
        ),
    )
    certifications = [row for row in rows if row["representation_asserted"] == "true"]
    assert certifications
    assert all(
        row["certified_representative"] == "Brotherhood of Locomotive Engineers and Trainmen"
        for row in certifications
    )
    assert all(row["certified_representative"] == "" for row in rows if row not in certifications)

    unread = scrape_determinations(delay_seconds=0, fetch_html=fetch_html, read_documents=False)
    assert all(row["certified_representative"] == "" for row in unread)
