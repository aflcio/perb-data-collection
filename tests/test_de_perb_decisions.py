"""Tests for Delaware PERB year-indexed decision scrape parsing."""

from __future__ import annotations

import re
from pathlib import Path

from perb_data_collection.collectors.de_perb_decisions import (
    list_year_pages,
    parse_year_page,
    scrape_decisions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_list_year_pages() -> None:
    html = (FIXTURES / "de_perb_decisions_index.html").read_text()
    years = list_year_pages(html)
    assert years
    assert years[0][0] >= years[-1][0]


def test_parse_year_page_fixture() -> None:
    html = (FIXTURES / "de_perb_decisions_2026.html").read_text()
    rows = parse_year_page(
        html,
        decision_year="2026",
        page_url="https://perb.delaware.gov/2026-decisions/",
        scraped_at="2026-07-14T00:00:00+00:00",
    )
    assert len(rows) >= 3
    assert rows[0]["jurisdiction_state"] == "DE"
    assert rows[0]["pdf_url"].endswith(".pdf")
    assert rows[0]["case_number"]
    # Decision-type labels must not land in employer or city.
    assert all(
        not re.search(
            r"(?i)Order of Dismissal|Probable Cause|Unfair Labor Practice",
            row["employer_name"] or "",
        )
        for row in rows
    )
    assert all(row["jurisdiction_city"] == "" or "Decision" not in row["jurisdiction_city"] for row in rows)
    # -v- filenames yield a real party on at least one side.
    v_rows = [row for row in rows if "-v-" in row["pdf_url"].lower() or "-v." in row["pdf_url"].lower()]
    assert v_rows
    assert any(row["employer_name"] or row["union_name"] for row in v_rows)


def test_parties_from_legacy_filename() -> None:
    from perb_data_collection.collectors.de_perb_decisions import _parties_from_filename

    emp, union = _parties_from_filename(
        "1984-1-11-84-3-DS-Capital-Educators-Assn.pdf"
    )
    assert emp == ""
    assert "Capital Educators" in union

    emp, union = _parties_from_filename(
        "1984-1-3-84-1-1-DS-Seaford-School-Board.pdf"
    )
    assert "Seaford School Board" in emp
    assert union == ""


def test_scrape_decisions_with_fixtures() -> None:
    index = (FIXTURES / "de_perb_decisions_index.html").read_text()
    year = (FIXTURES / "de_perb_decisions_2026.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        if "2026" in url:
            return year
        if url.rstrip("/").endswith("decisions"):
            return index
        return "<html></html>"

    rows = scrape_decisions(fetch_html=fake_fetch)
    assert len(rows) >= 3
    assert all(
        not re.search(r"(?i)Probable Cause Determination", row["jurisdiction_city"] or "")
        for row in rows
    )
