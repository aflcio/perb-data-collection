"""NE CIR reporter: caption parties beat filename abbreviations (infra-75)."""

from pathlib import Path

from perb_data_collection.collectors.ne_cir_reporter import (
    enrich_row_from_decision_html,
    parse_decision_caption,
    parse_decision_filename,
    _scrub_employer_as_union,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_caption_parses_petitioner_union_and_respondent_employer():
    html = (FIXTURES / "ne_cir_decision_lincoln_firefighters.html").read_text()
    employer, union = parse_decision_caption(html)
    assert "CITY OF LINCOLN" in employer.upper()
    assert "FIREFIGHTERS" in union.upper()


def test_caption_parses_nape_vs_state():
    html = (FIXTURES / "ne_cir_decision_nape_corrections.html").read_text()
    employer, union = parse_decision_caption(html)
    assert "STATE OF NEBRASKA" in employer.upper()
    assert "NEBRASKA ASSOCIATION OF PUBLIC EMPLOYEES" in union.upper()


def test_enrich_overrides_filename_abbreviation():
    row = parse_decision_filename(
        "data/reporter/19/19_CIR_1__(2013)_Lincoln_Firefighters_Ass'n_City_of_Lincoln.htm",
        volume_dir="19_CIR_xx",
        volume_page_url="https://example/vol",
        scraped_at="2026-08-31T00:00:00+00:00",
    )
    assert row is not None
    html = (FIXTURES / "ne_cir_decision_lincoln_firefighters.html").read_text()
    enriched = enrich_row_from_decision_html(row, html)
    assert "CITY OF LINCOLN" in enriched["employer_name"].upper()
    assert "FIREFIGHTERS" in enriched["union_name"].upper()


def test_state_of_ne_is_not_left_in_union_column():
    employer, union = _scrub_employer_as_union("Something", "STATE OF NE")
    assert union == ""
    assert employer == "Something"
    employer2, union2 = _scrub_employer_as_union("", "STATE OF NE")
    assert union2 == ""
    assert "STATE OF NE" in employer2.upper()
