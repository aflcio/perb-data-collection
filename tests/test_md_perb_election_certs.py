"""Tests for Maryland PERB election certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from perb_data_collection.collectors.md_perb_election_certs import (
    _parse_listing_items,
    scrape_election_certifications,
)


def test_parse_listing_items_from_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "md_perb_election_certs_page.html").read_text()
    rows = _parse_listing_items(html, scraped_at="2026-07-09T00:00:00+00:00")
    assert len(rows) >= 30
    sample = rows[0]
    assert sample["canonical_case_type"] == "CERTIFICATION"
    assert sample["source_agency_code"] == "MD_PERB"
    assert sample["pdf_url"].startswith("https://laborboard.maryland.gov/")
    rows_by_key = {row["row_key"]: row for row in rows}
    assert rows_by_key["MD_PERB:418"]["employer_name"] == "Howard Community College"
    assert rows_by_key["MD_PERB:418"]["union_name"] == (
        "Service Employees International Union, Local 500"
    )
    assert rows_by_key["MD_PERB:379"]["case_number"] == "SHELRB EL 07-01"
    assert rows_by_key["MD_PERB:346"]["canonical_case_type"] == "ULP"
    assert rows_by_key["MD_PERB:418"]["document_description"] == (
        "Certification Of Representative"
    )


def test_scrape_election_certifications_uses_fixture() -> None:
    html = (Path(__file__).parent / "fixtures" / "md_perb_election_certs_page.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    rows = scrape_election_certifications(fetch_html=fake_fetch)
    assert len(rows) == 34
    row_keys = {row["row_key"] for row in rows}
    assert "MD_PERB:412" not in row_keys
    assert "MD_PERB:425" not in row_keys
    assert all(row["employer_name"] for row in rows)
    assert all(row["union_name"] for row in rows)


def test_scrape_raises_when_displayed_total_mismatches() -> None:
    html = (Path(__file__).parent / "fixtures" / "md_perb_election_certs_page.html").read_text()
    html = html.replace("Displaying 1 - 36 of 36 results.", "Displaying 1 - 36 of 99 results.")

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    with pytest.raises(RuntimeError, match="99 results"):
        scrape_election_certifications(fetch_html=fake_fetch)
