"""Tests for Illinois ILRB certification PDF parsing (infra-38)."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.il_ilrb_bargaining_certs import (
    _heal_shredded_fields,
    _jurisdiction_city,
    _strip_neighbor_bleed,
    parse_certs_text,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_heal_recovers_date_from_union() -> None:
    certified, employer, union, party = _heal_shredded_fields(
        certified="",
        employer="Village of Hinsdale",
        union="International 8/2/2024 Association of Fire Fighters",
        party="20",
    )
    assert certified == "8/2/2024"
    assert employer == "Village of Hinsdale"
    assert "8/2/2024" not in union
    assert "Fire Fighters" in union
    assert party == ""


def test_heal_does_not_invent_truncated_year() -> None:
    certified, _employer, union, _party = _heal_shredded_fields(
        certified="",
        employer="City of Troy",
        union="IAFF 05/10/202 Local 123",
        party="",
    )
    assert certified == ""
    assert "05/10/202" in union


def test_jurisdiction_city_skips_shredded_employer() -> None:
    assert _jurisdiction_city("City of Venice Local") == "Venice"
    assert _jurisdiction_city("Declaration of Disinterest City of Troy") == ""
    assert _jurisdiction_city("Village of Hinsdale") == "Hinsdale"


def test_strip_neighbor_bleed_removes_next_employer_suffix() -> None:
    rows = [
        {
            "employer_name": "Kankakee, City of Geneva Public Library",
            "union_name": "Illinois Fraternal Order of Police Labor Council",
            "jurisdiction_city": "",
        },
        {
            "employer_name": "Geneva Public Library District",
            "union_name": "American Federation of State, County, and Municipal Employees, Council 31",
            "jurisdiction_city": "",
        },
    ]
    healed = _strip_neighbor_bleed(rows)
    assert healed[0]["employer_name"] == "Kankakee, City of"
    assert "Geneva" not in healed[0]["employer_name"]


def test_fy27_wrap_bleed_cases() -> None:
    text = (FIXTURES / "il_ilrb_fy27_snippet.txt").read_text()
    rows = parse_certs_text(
        text,
        fiscal_year="FY27",
        pdf_url="https://example.test/fy27.pdf",
        scraped_at="2026-08-28T00:00:00+00:00",
    )
    by_case = {r["case_number"]: r for r in rows}

    assert by_case["S-RC-26-079"]["employer_name"] == "Carbondale, City of"
    assert "Fraternal Order of Police" in by_case["S-RC-26-079"]["union_name"]
    assert "Service Employees" not in by_case["S-RC-26-079"]["union_name"]
    assert by_case["S-RC-26-079"]["certified_date"] == "7/9/2026"

    assert by_case["L-RC-26-015"]["employer_name"] == "Cook, County of"
    assert "Service Employees International Union" in by_case["L-RC-26-015"]["union_name"]
    assert "Machinist" not in by_case["L-RC-26-015"]["union_name"]

    assert "Pike County Circuit Clerk" in by_case["S-RC-26-094"]["employer_name"]
    assert "Machinist" in by_case["S-RC-26-094"]["union_name"]

    assert by_case["S-RC-27-004"]["employer_name"] == "Kankakee, City of"
    assert "Fraternal Order of Police" in by_case["S-RC-27-004"]["union_name"]
    assert "American Federation" not in by_case["S-RC-27-004"]["union_name"]
    assert "Geneva" not in by_case["S-RC-27-004"]["employer_name"]

    assert "Geneva Public Library" in by_case["S-RC-26-088"]["employer_name"]
    assert "Council 31" in by_case["S-RC-26-088"]["union_name"]
    assert by_case["S-RC-26-088"]["certified_date"] == "8/4/2026"

    assert all(r["certified_date"] for r in rows)
    assert not any((r["prevailing_party"] or "").isdigit() for r in rows)


def test_fy14_shred_snippet_recovers_date_and_iuoe() -> None:
    text = (FIXTURES / "il_ilrb_fy14_shred_snippet.txt").read_text()
    rows = parse_certs_text(
        text,
        fiscal_year="FY14",
        pdf_url="https://example.test/fy14.pdf",
        scraped_at="2026-08-28T00:00:00+00:00",
    )
    by_case = {r["case_number"]: r for r in rows}
    assert "S-RC-14-008" in by_case
    row = by_case["S-RC-14-008"]
    assert row["certified_date"] == "8/29/2013"
    assert "Operating Engineers" in row["union_name"]
    assert "8/" not in row["union_name"] or "8/29" in row["certified_date"]
