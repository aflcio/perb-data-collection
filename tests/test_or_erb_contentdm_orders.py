"""OR ERB ContentDM: Official Case Name order is procedural, not a role."""

from __future__ import annotations

from perb_data_collection.collectors.or_erb_contentdm_orders import (
    _parties,
    parse_query_page,
)

_PAYLOAD = {
    "pager": {"total": 4},
    "records": [
        {
            "pointer": "101",
            "title": "UP-012-20 Order",
            "subjec": "Service Employees International Union Local 503 v. State of Oregon",
            "type": "Unfair Labor Practice",
            "date": "2020-06-01",
        },
        {
            "pointer": "102",
            "title": "RC-003-19 Order",
            "subjec": (
                "City of Portland v. Portland Police Commanding Officers "
                "Association (PPCOA)"
            ),
            "type": "Representation/Unit Clarification",
            "date": "2019-04-02",
        },
        {
            "pointer": "103",
            "title": "UP-050-18 Order",
            "subjec": "Jane Doe v. Oregon School Employees Association",
            "type": "Unfair Labor Practice",
            "date": "2018-11-15",
        },
        {
            "pointer": "104",
            "title": "UP-070-17 Order",
            "subjec": "Marion County v. Multnomah County",
            "type": "Unfair Labor Practice",
            "date": "2017-02-20",
        },
    ],
}


def test_ulp_caption_union_first() -> None:
    assert _parties(
        "Service Employees International Union Local 503 v. State of Oregon",
        "Unfair Labor Practice",
    ) == ("State of Oregon", "Service Employees International Union Local 503")


def test_representation_caption_employer_first() -> None:
    employer, union = _parties(
        "City of Portland v. Portland Police Commanding Officers Association (PPCOA)",
        "Representation/Unit Clarification",
    )
    assert employer == "City of Portland"
    assert union.startswith("Portland Police Commanding Officers Association")


def test_no_positional_fallback_when_both_sides_are_public() -> None:
    assert _parties("Marion County v. Multnomah County", "Unfair Labor Practice") == ("", "")


def test_single_party_case_name_assigns_nothing() -> None:
    assert _parties("In the Matter of Lane Community College", "Declaratory Ruling") == ("", "")


def test_parse_query_page_roles() -> None:
    rows = parse_query_page(_PAYLOAD, scraped_at="2026-09-10T00:00:00+00:00")
    by_pointer = {row["contentdm_pointer"]: row for row in rows}
    assert len(rows) == 4

    assert by_pointer["101"]["employer_name"] == "State of Oregon"
    assert "Local 503" in by_pointer["101"]["union_name"]

    assert by_pointer["102"]["employer_name"] == "City of Portland"
    assert by_pointer["102"]["jurisdiction_city"] == "Portland"

    individual = by_pointer["103"]
    assert individual["employer_name"] == ""
    assert individual["union_name"] == "Oregon School Employees Association"
    assert individual["official_case_name"] == "Jane Doe v. Oregon School Employees Association"

    both_public = by_pointer["104"]
    assert both_public["employer_name"] == ""
    assert both_public["union_name"] == ""


def test_separator_spacing_the_index_uses() -> None:
    assert _parties(
        "AFSCME Local 3512 v.Willamalane Park and Recreation District"
    ) == ("Willamalane Park and Recreation District", "AFSCME Local 3512")
    assert _parties(
        "Portland Community College Faculty Federation, Local 2277 AFT-Oregon, "
        "AFL-CIO NOLC (PCCFF)v. Portland Community College (PCC)"
    )[0] == "Portland Community College (PCC)"
    assert _parties("Salem Education Association v, Salem-Keizer School District 24J") == (
        "Salem-Keizer School District 24J",
        "Salem Education Association",
    )
    assert _parties(
        "Baltus et al V. Multnomah County School District 1J and Portland "
        "Association of Teachers (PAT)"
    ) == ("Multnomah County School District 1J", "Portland Association of Teachers (PAT)")
    # A "v" inside a word is not a separator.
    assert _parties("Kovach v. City of Salem") == ("City of Salem", "")


def test_cross_petitions_captioned_twice() -> None:
    assert _parties(
        "Polk County v. Polk County Deputy Sheriff's Association and Polk County "
        "Deputy Sheriff's Association v. Polk County"
    ) == ("Polk County", "Polk County Deputy Sheriff's Association")
    assert _parties(
        "Morrow County Education Association v. Morrow County School District and "
        "Morrow County School District v. Morrow County Education Association"
    ) == ("Morrow County School District", "Morrow County Education Association")
    assert _parties(
        "Haskins v. State of Oregon, Oregon State Hospital (OSH) and Haskins v. "
        "Oregon Public Employees Union (OPEU)"
    ) == ("State of Oregon, Oregon State Hospital (OSH)", "Oregon Public Employees Union (OPEU)")


def test_three_parties_in_one_caption() -> None:
    # "and" inside a union's own name is not a caption boundary.
    assert _parties(
        "Grisham-Tittle v. American Federation of State, County and Municipal "
        "Employees (AFSCME), Local 1246-3 v. State of Oregon, Department of "
        "Administrative Services (DAS)"
    ) == (
        "State of Oregon, Department of Administrative Services (DAS)",
        "American Federation of State, County and Municipal Employees (AFSCME), Local 1246-3",
    )


def test_joint_petition_needs_both_roles() -> None:
    assert _parties(
        "Petition Jointly Filed by Corvallis School District 509J and Mid-Valley "
        "Bargaining Council"
    ) == ("Corvallis School District 509J", "Mid-Valley Bargaining Council")
    assert _parties("Petition for Declaratory Ruling Filed by City of Medford") == ("", "")
