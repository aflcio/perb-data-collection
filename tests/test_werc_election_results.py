"""WERC annual recertification tallies: a tally is not a certification.

Fixtures are the real PDFs' ``pdftotext -layout`` text.
"""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.werc_election_results import (
    ENDPOINT_TALLY,
    _parse_result_text,
    parse_tally_line,
)

FIXTURES = Path(__file__).parent / "fixtures"
SPRING_2026 = "https://werc.wi.gov/doaroot/2026WERCSpringFinalResults.pdf"
FALL_2025 = "https://werc.wi.gov/doaroot/2025WERCFallElectionResults.pdf"


def _rows(fixture: str, url: str) -> dict[str, dict[str, str]]:
    text = (FIXTURES / fixture).read_text()
    rows = _parse_result_text(text, pdf_url=url, scraped_at="2026-09-29T00:00:00+00:00")
    return {row["unit_code"]: row for row in rows}


def test_bennett_zero_vote_tally_is_a_tally_that_fails_the_threshold() -> None:
    row = _rows("werc_2026_spring_tally_layout.txt", SPRING_2026)["360.0011"]
    assert row["employer_name"] == "Bennett/Town of"
    assert row["union_name"] == "IUOE Local 139"
    assert (row["unit_population"], row["votes_cast"], row["votes_yes"], row["votes_no"]) == (
        "2", "0", "0", "0",
    )
    assert row["meets_51pct_threshold"] == "false"
    # The document is the board's tally, published before challenges close.
    assert row["document_status"] == ENDPOINT_TALLY
    assert row["tally_as_of"] == "12:00PM APRIL 28"
    assert (row["election_open_date"], row["election_close_date"]) == ("2026-04-08", "2026-04-28")


def test_threshold_is_51_percent_of_the_unit_not_of_ballots_cast() -> None:
    row = _rows("werc_2026_spring_tally_layout.txt", SPRING_2026)["379.0018"]
    assert (row["unit_population"], row["votes_cast"], row["votes_yes"], row["votes_no"]) == (
        "89", "66", "63", "3",
    )
    # 63 / 89 = 70.8% of the unit.
    assert row["meets_51pct_threshold"] == "true"
    assert row["document_status"] == ENDPOINT_TALLY


def test_filled_challenged_columns_do_not_slide_the_tally() -> None:
    rows = _rows("werc_2025_fall_tally_layout.txt", FALL_2025)
    assert len(rows) == 252
    beaver_dam = rows["101.0013"]
    assert (
        beaver_dam["unit_population"],
        beaver_dam["votes_cast"],
        beaver_dam["votes_yes"],
        beaver_dam["votes_no"],
        beaver_dam["challenged_unit_population"],
        beaver_dam["challenged_votes"],
    ) == ("253", "219", "218", "1", "1", "1")
    assert beaver_dam["bargaining_unit_name"] == "teacher"


def test_every_spring_2026_unit_row_is_parsed() -> None:
    text = (FIXTURES / "werc_2026_spring_tally_layout.txt").read_text()
    rows = _parse_result_text(text, pdf_url=SPRING_2026, scraped_at="x")
    assert len(rows) == 70
    assert all(row["document_status"] == ENDPOINT_TALLY for row in rows)


def test_unit_name_ending_in_a_number_is_not_eaten_by_the_tally() -> None:
    line = (
        "322.0021 Altoona/City of                             Teamsters Local 662"
        "                                             DPW 2                                 10"
        "           10          10         0"
    )
    row = parse_tally_line(line)
    assert row is not None
    assert row["bargaining_unit_name"] == "DPW 2"
    assert (row["unit_population"], row["votes_cast"]) == ("10", "10")
