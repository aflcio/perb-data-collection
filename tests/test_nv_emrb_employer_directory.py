"""Tests for NV EMRB employer directory parsing, in particular the guards
against a contact's first name sliding into the union column and a wrapped
"AFL-CIO" tail surviving as a bare fragment."""

from __future__ import annotations

from perb_data_collection.collectors.nv_emrb_employer_directory import (
    _looks_like_bare_affiliation_fragment,
    _looks_like_contact_name,
    _scrub_union_name,
    parse_employer_text,
)

PDF_URL = "https://emrb.nv.gov/uploadedFiles/emrbnvgov/content/Local_Government_Employer_Data.pdf"
SCRAPED_AT = "2026-09-10T00:00:00+00:00"


def _rows(text: str) -> list[dict[str, str]]:
    return parse_employer_text(text, pdf_url=PDF_URL, scraped_at=SCRAPED_AT)


def test_contact_first_name_slides_into_union_column_is_emptied() -> None:
    # Union column is genuinely blank in the source; pdftotext -layout
    # slides the contact's first name ("Colin") under it.
    text = (
        "City of Reno    Colin  Smith  123 Main St  Reno  NV  89501  "
        "Colin  Some Unit\n"
    )
    rows = _rows(text)
    assert len(rows) == 1
    row = rows[0]
    assert row["contact_name"] == "Colin Smith"
    assert row["union_name"] == ""
    assert row["bargaining_unit_name"] == "Some Unit"


def test_wrapped_afl_cio_fragment_does_not_become_union() -> None:
    text = (
        "City of Sparks    Jane  Doe  456 Oak Ave  Sparks  NV  89431  "
        "IBEW Local 1245  Unit A\n"
        "                              AFL-CIO\n"
    )
    rows = _rows(text)
    assert len(rows) == 1
    row = rows[0]
    assert row["union_name"] == "IBEW Local 1245"
    assert all(row["union_name"] != "AFL-CIO" for row in rows)
    assert all("CIO" not in row["union_name"].split() for row in rows if row["union_name"])


def test_bare_cio_on_primary_row_is_emptied() -> None:
    text = (
        "City of Elko    Mike  Ryan  789 Pine  Elko  NV  89801  "
        "CIO  Unit C\n"
    )
    rows = _rows(text)
    assert len(rows) == 1
    assert rows[0]["union_name"] == ""
    assert rows[0]["bargaining_unit_name"] == "Unit C"


def test_short_capitalised_non_org_word_is_emptied_even_without_contact_match() -> None:
    text = (
        "City of Fallon    Amy  Lee  10 Elm St  Fallon  NV  89406  "
        "Susan  Unit D\n"
    )
    rows = _rows(text)
    assert len(rows) == 1
    assert rows[0]["contact_name"] == "Amy Lee"
    assert rows[0]["union_name"] == ""


def test_real_union_with_org_token_is_kept() -> None:
    text = (
        "City of Sparks    Jane  Doe  456 Oak Ave  Sparks  NV  89431  "
        "IBEW Local 1245  Unit A\n"
    )
    rows = _rows(text)
    assert rows[0]["union_name"] == "IBEW Local 1245"


def test_looks_like_contact_name_helper() -> None:
    assert _looks_like_contact_name("Colin", "Colin Smith")
    assert _looks_like_contact_name("Smith", "Colin Smith")
    assert _looks_like_contact_name("Colin Smith", "Colin Smith")
    assert not _looks_like_contact_name("IBEW Local 1245", "Colin Smith")


def test_looks_like_bare_affiliation_fragment_helper() -> None:
    for fragment in ("CIO", "AFL", "AFL-CIO", "AFL CIO", "-CIO"):
        assert _looks_like_bare_affiliation_fragment(fragment)
    assert not _looks_like_bare_affiliation_fragment("IBEW Local 1245")
    assert not _looks_like_bare_affiliation_fragment("SEIU")


def test_scrub_union_name_passthrough_for_real_union() -> None:
    assert _scrub_union_name("Teamsters Local 14", "Colin Smith") == "Teamsters Local 14"
