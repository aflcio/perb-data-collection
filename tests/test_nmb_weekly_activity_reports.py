from collections import Counter
from pathlib import Path

import pytest

from perb_data_collection.collectors.nmb_weekly_activity_reports import (
    ARCHIVE_URL,
    MAX_ROW_KEY_LENGTH,
    BASE_URL,
    CURRENT_URL,
    WIDE_FIELDNAMES,
    _assign_row_keys,
    _split_cases,
    classify_section,
    discover_report_urls,
    discover_year_page_urls,
    parse_report,
    parse_report_week,
    scrape_weekly_reports,
    split_approx_craft,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(name: str, url: str = f"{BASE_URL}report/") -> tuple[list[dict[str, str]], Counter[str]]:
    stats: Counter[str] = Counter()
    rows = parse_report(
        _fixture(name), source_url=url, source_page_url=ARCHIVE_URL,
        scraped_at="2026-09-29T00:00:00+00:00", stats=stats,
    )
    return rows, stats


def _row(rows: list[dict[str, str]], case_number: str, section: str) -> dict[str, str]:
    return next(row for row in rows if row["case_number"] == case_number and row["section"] == section)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("WEEKLY ACTIVITY REPORT November 15 — November 19, 2010", ("2010-11-15", "2010-11-19")),
        ("NMB Weekly Activity Report Week Ending July 9, 1999", ("", "1999-07-09")),
        ("December 29, 2025 – January 2, 2026", ("2025-12-29", "2026-01-02")),
        ("September 4-8, 2006", ("2006-09-04", "2006-09-08")),
        ("December 20 through 24, 1999", ("1999-12-20", "1999-12-24")),
        ("Weekly Activity Report Janurary 1-5, 2024", ("2024-01-01", "2024-01-05")),
        (f"{BASE_URL}weekly-activity-report-july-5-9-2004/", ("2004-07-05", "2004-07-09")),
        (f"{BASE_URL}weekly-activity-report-december-6-dec-10-2010-2/", ("2010-12-06", "2010-12-10")),
    ],
)
def test_report_week_formats(text: str, expected: tuple[str, str]) -> None:
    assert parse_report_week(text) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("A-13586", ["A-13586"]),
        ("A12882", ["A-12882"]),  # 1998, no dash
        ("A-12798& A-12803", ["A-12798", "A-12803"]),
        ("A-12897-99", ["A-12897", "A-12898", "A-12899"]),  # a printed range
        ("A-13584 A-13586 A-13587", ["A-13584", "A-13586", "A-13587"]),
        ("GM-83", ["GM-0083"]),  # the GM and T series are printed padded and unpadded
        ("T-515", ["T-0515"]),
        ("R-7626 10/02/24", ["R-7626"]),  # the docket date is not a case
        ("Several", []),
    ],
)
def test_case_cells(cell: str, expected: list[str]) -> None:
    assert [case for case, _prefix, _date in _split_cases(cell)] == expected


def test_case_cell_keeps_its_docket_date() -> None:
    assert _split_cases("R-7626 10/02/24") == [("R-7626", "R", "2024-10-02")]


@pytest.mark.parametrize(
    ("label", "section"),
    [
        ("New Dockets:", "mediation_new_docket"),
        ("Mediation Cases Assigned/Reassigned: None", "mediation_assigned"),
        ("Settlements:", "mediation_settlement"),
        ("Ratifications:", "mediation_settlement"),
        ("Cooling-Off Periods/Strike Activity: None", "mediation_released"),
        ("Meetings, Training, and Facilitation:", "mediation_meeting"),
        ("New Applications:", "representation_application"),
        ("Ballot Instructions Mailed:", "ballots_mailed"),
        ("Elections Underway:", "election_underway"),
        ("Case Closed: None", "case_closed"),
        ("ARBITRATION (estimates)", "arbitration"),
        ("ABRITRATION:", "arbitration"),
        ("October 1, 2009 through November 12, 2010", ""),
    ],
)
def test_section_labels(label: str, section: str) -> None:
    assert classify_section(label) == section


def test_approx_craft_cell() -> None:
    assert split_approx_craft("335-Mechanics and Related Employees") == ("335", "Mechanics and Related Employees")
    assert split_approx_craft("16,500- Passenger Service") == ("16500", "Passenger Service")
    assert split_approx_craft("17 – Train and Engine Service") == ("17", "Train and Engine Service")
    assert split_approx_craft("Pilots") == ("", "Pilots")


def test_2010_report_sections_and_columns() -> None:
    rows, stats = _parse("nmb_war_2010-11-19.html")
    assert len(rows) == 10
    docket = _row(rows, "A-13586", "mediation_new_docket")
    assert (docket["employer_name"], docket["union_name"], docket["craft_class"]) == (
        "Continental Airlines", "IAM", "Flight Attendants",
    )
    assert (docket["report_week_start"], docket["report_week_end"]) == ("2010-11-15", "2010-11-19")
    assert docket["case_prefix"] == "A"
    assert docket["native_case_type"] == "New Dockets"
    assert docket["mediator_or_investigator"] == "Sims"
    assert _row(rows, "A-13379", "mediation_settlement")["status"] == "TA Ratified"
    application = _row(rows, "CR-6999", "representation_application")
    assert (application["approx_employees"], application["craft_class"]) == ("2200", "Office and Clerical Employees")
    assert application["canonical_case_type"] == "CERTIFICATION"
    election = _row(rows, "R-7257", "election_underway")
    assert (election["approx_employees"], election["count_date"]) == ("16500", "2010-12-07")
    assert _row(rows, "R-7256", "case_closed")["disposition"] == "Dismissal"
    # The arbitration caseload table carries no cases and is skipped.
    assert not any(row["employer_name"] in {"NRAB", "PLB", "SBA"} for row in rows)
    assert stats["rows_without_section"] == 0


def test_1998_header_printed_as_its_own_table() -> None:
    rows, _stats = _parse("nmb_war_1998-10-30.html")
    settlements = [row for row in rows if row["section"] == "mediation_settlement"]
    assert [row["case_number"] for row in settlements] == ["A-12674", "A-12882", "A-12798", "A-12803", "A-12910"]
    assert settlements[0]["status"] == "Ag-Med"
    assert _row(rows, "R-6621", "election_underway")["union_name"] == "IAM-AMFA"
    assert _row(rows, "R-6519", "case_closed")["disposition"] == "Findings Upon Investigation- Dismissal"
    assert all(row["report_week_end"] == "1998-10-30" and row["report_week_start"] == "" for row in rows)


def test_1999_one_cell_per_row_tables_are_regrouped() -> None:
    rows, _stats = _parse("nmb_war_1999-05-21.html")
    docket = _row(rows, "A-13035", "mediation_new_docket")
    assert (docket["employer_name"], docket["union_name"], docket["craft_class"]) == (
        "Southeastern Penn. Trans. Authority", "UTU", "Conductors & Asst. Conductors",
    )
    assert _row(rows, "A-12957", "mediation_settlement")["status"] == "Ratified"


def test_unrecognised_heading_does_not_inherit_the_section_above() -> None:
    # 2022: "New Dockets: None" then "Ratifications:" -- the METRA row is a
    # ratification, not a new docket.
    rows, _stats = _parse("nmb_war_2022-02-11.html")
    metra = next(row for row in rows if row["case_number"] == "A-13994")
    assert metra["section"] == "mediation_settlement"
    assert (metra["union_name"], metra["craft_class"]) == ("BLET", "Locomotive Engineers")
    assert not any(row["section"] == "mediation_new_docket" for row in rows)


def test_2024_training_cases_and_combined_case_docket_column() -> None:
    rows, _stats = _parse("nmb_war_2024-02-16.html")
    training = _row(rows, "T-0515", "mediation_meeting")
    assert (training["employer_name"], training["union_name"]) == ("Norse Atlantic Airways", "AFA")
    application = _row(rows, "R-7626", "representation_application")
    assert (application["approx_employees"], application["craft_class"]) == ("17", "Train and Engine Service")
    assert (application["report_week_start"], application["report_week_end"]) == ("2024-02-12", "2024-02-16")


def test_dead_report_link_yields_nothing() -> None:
    stats: Counter[str] = Counter()
    html = "<html><head><title>Page not found &#8211; National Mediation Board</title></head><body></body></html>"
    assert parse_report(html, source_url="u", source_page_url="p", scraped_at="t", stats=stats) == []
    assert stats["dead_report_links"] == 1


def test_discovers_drifting_year_page_paths() -> None:
    urls = discover_year_page_urls(_fixture("nmb_war_archive_index.html"))
    assert urls[0] == f"{BASE_URL}1998-weekly-activity-reports/"
    assert f"{BASE_URL}2023-weekly-activity-report/" in urls
    assert f"{ARCHIVE_URL}2024-weekly-activity-reports/" in urls
    assert ARCHIVE_URL not in urls
    assert len(urls) == len(set(urls)) == 28


def test_discovers_report_links_including_bare_post_ids() -> None:
    urls = discover_report_urls(_fixture("nmb_war_2024_year_page.html"), index_url=f"{ARCHIVE_URL}2024-weekly-activity-reports/")
    assert f"{BASE_URL}19048-2/" in urls  # linked as "Weekly Activity Report ..." with no week in the slug
    assert ARCHIVE_URL not in urls
    assert len(urls) == len(set(urls))


def test_scrape_assigns_unique_keys_and_drops_a_repeated_report() -> None:
    report = _fixture("nmb_war_2010-11-19.html")
    archive = f'<div class="entry-content"><a href="{BASE_URL}2010-weekly-activity-reports/">2010</a></div><!-- .entry-content -->'
    year = (
        '<div class="entry-content">'
        f'<a href="{BASE_URL}weekly-activity-report-november-15-november-19-2010/">11-19-2010: Weekly Activity Report</a>'
        f'<a href="{BASE_URL}weekly-activity-report-november-15-november-19-2010-2/">11-19-2010: Weekly Activity Report</a>'
        "</div><!-- .entry-content -->"
    )
    pages = {
        ARCHIVE_URL: archive,
        f"{BASE_URL}2010-weekly-activity-reports/": year,
        CURRENT_URL: '<div class="entry-content"></div><!-- .entry-content -->',
        f"{BASE_URL}weekly-activity-report-november-15-november-19-2010/": report,
        f"{BASE_URL}weekly-activity-report-november-15-november-19-2010-2/": report,
    }
    rows = scrape_weekly_reports(delay_seconds=0, fetch_html=lambda url, delay_seconds=0: pages[url])
    assert len(rows) == 10  # the second URL repeats the first report and is dropped
    assert len({row["row_key"] for row in rows}) == len(rows)
    docket = _row(rows, "A-13586", "mediation_new_docket")
    assert docket["row_key"] == "NMB-WAR:2010-11-19:MEDIATION-NEW-DOCKET:A-13586:IAM:FLIGHT-ATTENDANTS"
    assert set(docket) >= set(WIDE_FIELDNAMES)


def test_scrape_refuses_an_empty_archive() -> None:
    with pytest.raises(RuntimeError):
        scrape_weekly_reports(delay_seconds=0, fetch_html=lambda url, delay_seconds=0: "<html></html>")


def test_long_craft_lists_keep_row_keys_within_128_characters() -> None:
    craft = "Apprentices, Car Inspectors, Car Repairmen, Electricians, Electronic Specialists, General Maintainers and Machinists"
    row = {
        "report_week_end": "2000-06-16", "section": "representation_application",
        "case_number": "CR-6691", "union_name": "RITU-TCU", "craft_class": craft,
    }
    rows = [dict(row), dict(row), {**row, "craft_class": craft + " and Helpers"}]
    _assign_row_keys(rows)
    keys = [r["row_key"] for r in rows]
    assert all(len(key) <= MAX_ROW_KEY_LENGTH for key in keys)
    assert len(set(keys)) == 3
    assert keys[0].startswith("NMB-WAR:2000-06-16:REPRESENTATION-APPLICATION:CR-6691:RITU-TCU:APPRENTICES")
    assert keys[1] == keys[0] + ":2"
    # Deterministic: the same printed row gets the same key on every run.
    again = [dict(row)]
    _assign_row_keys(again)
    assert again[0]["row_key"] == keys[0]
    # Short keys are untouched.
    short = [{**row, "craft_class": "Pilots"}]
    _assign_row_keys(short)
    assert short[0]["row_key"] == "NMB-WAR:2000-06-16:REPRESENTATION-APPLICATION:CR-6691:RITU-TCU:PILOTS"
