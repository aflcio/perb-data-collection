"""Tests for Vermont VLRB volume-decision filename party parsing (infra-35)."""

from __future__ import annotations

from perb_data_collection.collectors.vt_vlrb_volume_decisions import (
    _parties_from_rest,
    parse_pdf_name,
)


def test_grievant_surname_clears_union_name() -> None:
    employer, union = _parties_from_rest("Gr. of Greenia")
    assert employer == "State of Vermont"
    assert union == ""

    employer, union = _parties_from_rest("Gr of Merrill")
    assert employer == "State of Vermont"
    assert union == ""


def test_union_brought_grievance_keeps_union_name() -> None:
    employer, union = _parties_from_rest("Gr. of VSEA")
    assert employer == "State of Vermont"
    assert union == "Gr. of VSEA"

    employer, union = _parties_from_rest("Gr. of AFSCME Local 1201")
    assert employer == "State of Vermont"
    assert "AFSCME" in union

    employer, union = _parties_from_rest("Gr. of IBEW Local 300")
    assert employer == "State of Vermont"
    assert "IBEW" in union

    employer, union = _parties_from_rest("Gr. of VSCFF Local 3180")
    assert employer == "State of Vermont"
    assert "VSCFF" in union


def test_v_split_unchanged() -> None:
    employer, union = _parties_from_rest("Rutland EA v. Rutland Sch. Bd")
    assert employer == "Rutland Sch. Bd"
    assert union == "Rutland EA"


def test_parse_pdf_name_grievant_keeps_caption_in_title() -> None:
    row = parse_pdf_name(
        "22-18-Gr. of Greenia.pdf",
        volume_number="22",
        volume_label="Volume 22",
        zip_url="https://example.test/Volume22.zip",
        scraped_at="2026-08-31T00:00:00+00:00",
    )
    assert row["employer_name"] == "State of Vermont"
    assert row["union_name"] == ""
    assert "Greenia" in row["document_title"]
    assert row["canonical_case_type"] == "ARBITRATION"
