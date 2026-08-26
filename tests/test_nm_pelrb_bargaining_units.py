"""Tests for New Mexico PELRB bargaining-unit roster parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.nm_pelrb_bargaining_units import parse_units_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_units_text_fixture() -> None:
    text = (FIXTURES / "nm_pelrb_bargaining_units.txt").read_text()
    # Pretend the live PDF filename so as-of falls back if header missing.
    rows = parse_units_text(
        "All Known State and Local Public Bargaining Units (Updated Feb. 2026)\n"
        + text,
        pdf_url=(
            "https://www.pelrb.nm.gov/wp-content/uploads/2026/03/"
            "All-Known-State-and-Local-Public-Bargaining-Units-Feb-2026.pdf"
        ),
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    by_key = {row["row_key"]: row for row in rows}

    anthony = by_key["NM_PELRB:pelrb_local:ANTHONY_CITY_OF:a"]
    assert anthony["employer_name"] == "Anthony, City of"
    assert anthony["union_name"] == ""
    assert "Police Dept" in anthony["bargaining_unit_name"]
    assert anthony["approx_employees"] == "10"
    assert anthony["jurisdiction_city"] == "Anthony"
    assert anthony["roster_as_of_date"] == "2026-02-01"

    bernalillo = by_key["NM_PELRB:pelrb_local:BERNALILLO_COUNTY:a"]
    assert bernalillo["jurisdiction_city"] == ""
    assert bernalillo["union_name"].startswith("AFSCME")

    abq = by_key["NM_PELRB:pelrb_local:ALBUQUERQUE_CITY_OF:a"]
    assert abq["jurisdiction_city"] == "Albuquerque"
    assert abq["approx_employees"] == "1200"

    deaf = next(
        row
        for row in rows
        if "SCHOOL_FOR_THE_DEAF" in row["row_key"] and row["unit_letter"] == "a"
    )
    assert "SCHOOL FOR THE DEAF" in deaf["employer_name"].upper()
    assert "Faculty and Staff Association" in deaf["union_name"]
    assert "Faculty and Staff Association" not in deaf["employer_name"]
    assert "Association" not in deaf["employer_name"]

    assert all(row["roster_as_of_date"] == "2026-02-01" for row in rows)
    assert not any(
        row["employer_name"] == row["jurisdiction_city"] and row["jurisdiction_city"]
        for row in rows
        if "County" in row["employer_name"] or "Schools" in row["employer_name"]
    )
