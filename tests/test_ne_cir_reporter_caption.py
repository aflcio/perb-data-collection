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


# --- 19 CIR 191 (2017): a real Word "Save as Web Page" export -------------

def test_word_export_metadata_and_entities_stay_out_of_the_parties():
    html = (FIXTURES / "ne_cir_19_cir_191_2017_ibew_1536_v_les.htm").read_text()
    employer, union = parse_decision_caption(html)
    assert union == "INTERNATIONAL BROTHERHOOD OF ELECTRICAL WORKERS, IBEW LOCAL 1536"
    assert employer == (
        "LINCOLN ELECTRIC SYSTEM, a division of the City of Lincoln, a municipal "
        "corporation and political subdivision of the state of Nebraska"
    )
    for junk in ("15.00", "EN-US", "X-NONE", "&nbsp", "nbsp", ")", "Respondent", "Case No"):
        assert junk not in employer and junk not in union


def test_word_export_case_number_and_filed_date():
    from perb_data_collection.collectors.ne_cir_reporter import parse_decision_document

    html = (FIXTURES / "ne_cir_19_cir_191_2017_ibew_1536_v_les.htm").read_text()
    parsed = parse_decision_document(html)
    # Source-wrapped across two lines ("Case" / "No. 1427"); it used to read 142.
    assert parsed["cir_case_number"] == "1427"
    assert (parsed["decision_date"], parsed["decision_date_precision"]) == ("2017-03-06", "day")


def test_enrich_marks_the_caption_as_the_party_source():
    row = parse_decision_filename(
        "data/reporter/19_CIR_xx/19_CIR_191_(2017)_IBEW_1536_v_LES.htm",
        volume_dir="19_CIR_xx",
        volume_page_url="https://example/vol",
        scraped_at="2026-09-29T00:00:00+00:00",
    )
    html = (FIXTURES / "ne_cir_19_cir_191_2017_ibew_1536_v_les.htm").read_text()
    enriched = enrich_row_from_decision_html(row, html)
    assert enriched["party_source"] == "caption"
    assert enriched["decision_date"] == "2017-03-06"
    assert enriched["decision_year"] == "2017"
    assert "IBEW LOCAL 1536" in enriched["union_name"]
