"""Tests for Maine MLRB unit/representation case parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.me_mlrb_unit_rep_cases import (
    parse_case_page,
    scrape_unit_rep_cases,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_afscme_petitioner_public_employer() -> None:
    html = (FIXTURES / "me_mlrb_12_uc_03.html").read_text()
    row = parse_case_page(
        filename="12-UC-03.htm",
        html=html,
        case_url="https://www.maine.gov/mlrb/decisions/rep/12-UC-03.htm",
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    assert row["employer_name"] == "PENOBSCOT COUNTY SHERIFF'S DEPARTMENT"
    assert "AFSCME" in row["union_name"]
    assert row["decision_date"] == "August 20, 2013"
    assert "v." not in row["employer_name"].lower()
    assert "No." not in row["employer_name"]


def test_parse_employer_as_petitioner() -> None:
    html = (FIXTURES / "me_mlrb_02_uc_01.html").read_text()
    row = parse_case_page(
        filename="02-UC-01.htm",
        html=html,
        case_url="https://www.maine.gov/mlrb/decisions/rep/02-UC-01.htm",
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    assert row["employer_name"] == "Town of Topsham"
    assert "IAMAW" in row["union_name"] or "Local S/89" in row["union_name"]
    assert row["decision_date"] == "December 21, 2001"


def test_parse_v_caption_uses_body_roles() -> None:
    html = (FIXTURES / "me_mlrb_08_uc_02.html").read_text()
    row = parse_case_page(
        filename="08-UC-02.htm",
        html=html,
        case_url="https://www.maine.gov/mlrb/decisions/rep/08-UC-02.htm",
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    assert row["employer_name"] == "MAINE MARITIME ACADEMY"
    assert "MAINE STATE EMPLOYEES ASSOCIATION" in row["union_name"]
    assert "v." not in row["employer_name"].lower()


def test_scrape_uses_fixtures() -> None:
    index = (
        '<html><a href="12-UC-03.htm">12-UC-03.htm</a>'
        '<a href="02-UC-01.htm">02-UC-01.htm</a></html>'
    )
    pages = {
        "12-UC-03.htm": (FIXTURES / "me_mlrb_12_uc_03.html").read_text(),
        "02-UC-01.htm": (FIXTURES / "me_mlrb_02_uc_01.html").read_text(),
    }

    def fake_fetch(url: str, **kwargs: object) -> str:
        if url.rstrip("/").endswith("rep"):
            return index
        for name, html in pages.items():
            if name in url:
                return html
        return "<html></html>"

    rows = scrape_unit_rep_cases(fetch_html=fake_fetch, delay_seconds=0)
    assert len(rows) == 2
    by_case = {row["case_number"]: row for row in rows}
    assert by_case["12-UC-03"]["employer_name"] == "PENOBSCOT COUNTY SHERIFF'S DEPARTMENT"
    assert by_case["02-UC-01"]["employer_name"] == "Town of Topsham"
