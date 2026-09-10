"""Tests for Illinois ILRB certification PDF parsing (infra-38)."""

from __future__ import annotations

import re
from pathlib import Path

from perb_data_collection.collectors.il_ilrb_bargaining_certs import (
    _heal_shredded_fields,
    _jurisdiction_city,
    _strip_neighbor_bleed,
    find_table_sections,
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


def test_fy14_sections_map_columns_per_table() -> None:
    """Each table in a volume gets its own header, so S-DE keeps no union."""
    text = (FIXTURES / "il_ilrb_fy14_sections_snippet.txt").read_text()
    sections = find_table_sections(text.split("\n"))
    headings = [heading for heading, _line, _cols in sections]
    assert "CERTIFICATIONS OF REPRESENTATIVE" in headings
    assert "AMENDMENT TO CERTIFICATIONS" in headings
    assert "REVOCATION OF CERTIFICATIONS" in headings
    designation = next(h for h in headings if "GUBERNATORIAL" in h)
    de_columns = next(
        cols for heading, _line, cols in sections if heading == designation
    )
    assert [role for role, _start in de_columns] == [
        "case",
        "employer",
        "certified",
        "agency",
        "employees",
        "unit",
    ]

    rows = parse_certs_text(
        text,
        fiscal_year="FY14",
        pdf_url="https://example.test/fy14.pdf",
        scraped_at="2026-09-10T00:00:00+00:00",
    )
    by_case = {row["case_number"]: row for row in rows}

    # The S-DE designation table has no Labor Organization column at all, and
    # its State Agency column used to be read as the union name.
    designated = by_case["S-DE-14-054"]
    assert designated["union_name"] == ""
    assert designated["agency"] == "Department of Corrections"
    assert designated["employer_name"] == "State of Illinois, DCMS"
    assert designated["certified_date"] == "09/19/2013"
    assert designated["employees"] == "1"
    assert designated["bargaining_unit_name"] == "Medical Administrator 4"
    assert "GUBERNATORIAL" in designated["table_heading"]

    # A blank line separates two independent designations; it is not a merge.
    assert "S-DE-14-055" in by_case

    # A representation row in the same file still carries its union.
    represented = by_case["S-RC-13-058"]
    assert represented["union_name"] == "Illinois FOP Labor Council"
    assert represented["agency"] == ""
    assert represented["table_heading"] == "CERTIFICATIONS OF REPRESENTATIVE"

    # The revocation table's employer names used to arrive scrambled.
    revoked = by_case["S-DD-14-002"]
    assert revoked["employer_name"] == "County of Jasper and Sheriff of Jasper County"
    assert revoked["union_name"] == "Laborers' Int'l Union of North America, Local 1280"
    assert revoked["table_heading"] == "REVOCATION OF CERTIFICATIONS"
    assert revoked["canonical_case_type"] == "DECERTIFICATION"


def test_no_fixture_row_has_a_date_shaped_union() -> None:
    fixtures = {
        "FY14": "il_ilrb_fy14_shred_snippet.txt",
        "FY14S": "il_ilrb_fy14_sections_snippet.txt",
        "FY27": "il_ilrb_fy27_snippet.txt",
    }
    for fiscal_year, name in fixtures.items():
        rows = parse_certs_text(
            (FIXTURES / name).read_text(),
            fiscal_year=fiscal_year,
            pdf_url="https://example.test/x.pdf",
            scraped_at="2026-09-10T00:00:00+00:00",
        )
        assert rows, name
        for row in rows:
            assert not re.search(r"\d{1,2}/\d", row["union_name"] or ""), (
                name,
                row["case_number"],
                row["union_name"],
            )
