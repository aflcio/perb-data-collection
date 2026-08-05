"""Tests for DC PERB certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.dc_perb_certifications import (
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

    rows = scrape_certifications(fetch_html=fake_fetch)
    assert len(rows) >= 5
