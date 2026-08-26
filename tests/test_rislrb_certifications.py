"""Tests for Rhode Island RISLRB certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.rislrb_certifications import (
    _parse_certification_table,
    scrape_certifications,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_certification_table_fixture() -> None:
    html = (FIXTURES / "rislrb_certifications_page.html").read_text()
    rows = _parse_certification_table(
        html,
        category="Firefighters",
        page_url="http://rislrb.ri.gov/FireFighterCert.htm",
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    assert len(rows) >= 5
    by_case = {row["case_number"]: row for row in rows}

    # Employer text is inside the anchor; must not fall back to href="…".
    barrington = by_case["EE-1792"]
    assert barrington["employer_name"] == "Barrington"
    assert "href=" not in barrington["employer_name"].lower()
    assert barrington["certification_pdf_url"].endswith("CertificationEE1792.pdf")
    assert barrington["jurisdiction_city"] == ""
    assert barrington["jurisdiction_state"] == "RI"
    assert barrington["row_key"] == "RI_RISLRB:EE-1792:Firefighters"

    albion = by_case["EE-3685"]
    assert "Albion" in albion["employer_name"]
    assert "Fire District" in albion["employer_name"]
    assert "href=" not in albion["employer_name"].lower()

    # Trailing unit text after </a> is kept with the link text, not alone.
    clerks = by_case["EE-3430"]
    assert clerks["employer_name"].startswith("Barrington")
    assert "Clerks" in clerks["employer_name"]
    assert not clerks["employer_name"].startswith("(")

    assert all("href=" not in row["employer_name"].lower() for row in rows)
    assert all(row["jurisdiction_city"] == "" for row in rows)


def test_scrape_certifications_uses_fixture() -> None:
    html = (FIXTURES / "rislrb_certifications_page.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    rows = scrape_certifications(fetch_html=fake_fetch, delay_seconds=0)
    # Eight listing pages × fixture rows, but row_key dedupes across categories.
    assert len(rows) >= 5
    assert all(row["source_agency_code"] == "RI_RISLRB" for row in rows)
    assert all("href=" not in row["employer_name"].lower() for row in rows)
    assert all(row["jurisdiction_city"] == "" for row in rows)
    assert len({row["row_key"] for row in rows}) == len(rows)
