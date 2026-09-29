"""Roles come from caption content, never from caption position."""

from __future__ import annotations

from perb_data_collection.party_roles import (
    distinct_parties,
    assign_roles,
    has_union_head,
    split_side,
    is_personal_name,
    is_public_employer,
    is_union,
)


def test_union_v_employer() -> None:
    assert assign_roles(
        "AFSCME District Council 89, Local 2026",
        "Borough of Ambler",
    ) == ("Borough of Ambler", "AFSCME District Council 89, Local 2026")


def test_employer_v_union() -> None:
    assert assign_roles(
        "Donegal Township",
        "International Union of Operating Engineers, Local 66",
    ) == ("Donegal Township", "International Union of Operating Engineers, Local 66")


def test_individual_v_union_leaves_employer_empty() -> None:
    assert assign_roles(
        "Jane Doe",
        "Pennsylvania State Education Association",
    ) == ("", "Pennsylvania State Education Association")


def test_individual_v_employer_leaves_union_empty() -> None:
    assert assign_roles("John Q. Smith", "City of Erie") == ("City of Erie", "")


def test_employer_v_employer_leaves_both_empty() -> None:
    assert assign_roles(
        "City of Portland",
        "Multnomah County",
    ) == ("", "")


def test_union_v_union_leaves_both_empty() -> None:
    assert assign_roles(
        "SEIU Local 503",
        "American Federation of Teachers, Local 111",
    ) == ("", "")


def test_named_pa_cases() -> None:
    employer, union = assign_roles(
        "Donegal Township",
        "International Union of Operating Engineers, Local 66",
    )
    assert employer == "Donegal Township"
    assert "Local 66" in union

    employer, union = assign_roles("Jane Doe", "Pennsylvania State Education Association")
    assert employer == ""
    assert union == "Pennsylvania State Education Association"


def test_individual_never_lands_in_either_column() -> None:
    for left, right in (
        ("Jane Doe", "Richard Roe"),
        ("Jane Doe", "Pennsylvania State Education Association"),
        ("John Q. Smith", "City of Erie"),
        ("Robert Jones Jr.", "Oregon Public Employees Union"),
    ):
        employer, union = assign_roles(left, right)
        assert employer not in {left, right} or not is_personal_name(employer)
        assert union not in {left, right} or not is_personal_name(union)


def test_classifiers() -> None:
    assert is_public_employer("Millcreek Township School District")
    assert is_public_employer("Commonwealth of Pennsylvania, Department of Corrections")
    assert not is_public_employer("Pennsylvania State Education Association")
    assert not is_public_employer("Portland Police Commanding Officers Association")

    assert is_union("Fraternal Order of Police, Lodge No. 5")
    assert is_union("Oregon School Employees Association")
    assert not is_union("City of Bend")

    assert is_personal_name("Jane Doe")
    assert is_personal_name("John Q. Smith")
    assert not is_personal_name("Donegal Township")
    assert not is_personal_name("SEIU Local 503")


def test_missing_or_blank_side_is_empty() -> None:
    assert assign_roles("", "City of Salem") == ("", "")
    assert assign_roles("SEIU Local 503", "") == ("", "")

# --- head noun beats the place or public token ---------------------------


def test_head_noun_makes_an_association_a_union() -> None:
    for name in (
        "Marion County Sheriff Sergeant's Association",
        "Crook County Deputy Sheriffs Association",
        "Benton County Deputy Sheriff's Association",
        "Lighthouse Education Association/OEA",
        "Linn-Benton-Lincoln Education Association-OEA-NEA",
        "Portland State University Chapter American Association of University "
        "Professors (PSU-AAUP)",
        "Medford Professional Employees Association",
        "Brookings Police Association",
        "AFSCME Local 88",
        "Portland Police Commanding Officers Association (PPCOA)",
    ):
        assert is_union(name), name
        assert not is_public_employer(name), name
        assert has_union_head(name), name


def test_an_association_can_never_be_filed_as_the_employer() -> None:
    employer, union = assign_roles(
        "Crook County Deputy Sheriffs Association",
        "Crook County",
    )
    assert employer == "Crook County"
    assert union == "Crook County Deputy Sheriffs Association"


def test_head_noun_captions_are_no_longer_empty() -> None:
    for left, right, employer, union in (
        (
            "Marion County Sheriff Sergeant's Association",
            "Marion County",
            "Marion County",
            "Marion County Sheriff Sergeant's Association",
        ),
        (
            "Benton County Deputy Sheriff's Association",
            "Benton County Sheriff's Department",
            "Benton County Sheriff's Department",
            "Benton County Deputy Sheriff's Association",
        ),
        (
            "Portland State University Chapter of the American Association of "
            "University Professors (PSU-AAUP)",
            "Portland State University (PSU)",
            "Portland State University (PSU)",
            "Portland State University Chapter of the American Association of "
            "University Professors (PSU-AAUP)",
        ),
    ):
        assert assign_roles(left, right) == (employer, union)


def test_employees_as_a_modifier_is_not_a_union_head() -> None:
    # "Employees" leads the name here; the head noun is the school district.
    assert not has_union_head("Certain Employees of Nyssa School District #26")
    assert is_public_employer("Certain Employees of Nyssa School District #26")


# --- public tokens -------------------------------------------------------


def test_additional_public_tokens() -> None:
    for name in (
        "Eugene Water & Electric Board",
        "Salem-Keizer School Board",
        "Lane ESD",
        "Oregon Charter School",
        "Oregon State Hospital",
        "Hood River Co.",
        "City of Portland Fire and Rescue Bureau",
        "Jackson County Fire District No. 3",
        "Multnomah County Library",
        "Housing Authority of Portland",
        "Northern Wasco County People's Utility District",
        "Port of Portland",
        "Tri-County Metropolitan Transit District",
        "Portland Parks and Recreation",
        "City of Sweet Home Public Works",
    ):
        assert is_public_employer(name), name
        assert not is_union(name), name


# --- compound sides ------------------------------------------------------


def test_compound_side_supplies_both_roles() -> None:
    assert assign_roles("Multnomah County and AFSCME Local 88", "Jepson") == (
        "Multnomah County",
        "AFSCME Local 88",
    )
    assert assign_roles(
        "City of Medford and Teamsters Local 223",
        "In the Matter of a Petition",
    ) == ("City of Medford", "Teamsters Local 223")
    assert split_side("City of Medford and Medford Municipal Employees Association") == (
        ["City of Medford"],
        ["Medford Municipal Employees Association"],
    )
    assert split_side(
        "Portland Firefighters' Association, Local 43 and City of Portland "
        "Fire and Rescue Bureau"
    ) == (
        ["City of Portland Fire and Rescue Bureau"],
        ["Portland Firefighters' Association, Local 43"],
    )


def test_and_inside_a_single_name_is_not_a_party_separator() -> None:
    # "Fire and Rescue" and "Water & Electric" stay whole: the halves do not
    # each classify, so the split is not proven.
    assert split_side("City of Portland Fire and Rescue Bureau") == (
        ["City of Portland Fire and Rescue Bureau"],
        [],
    )
    assert split_side("Eugene Water & Electric Board") == (
        ["Eugene Water & Electric Board"],
        [],
    )
    assert split_side(
        "American Federation of State, County and Municipal Employees (AFSCME)"
    ) == ([], ["American Federation of State, County and Municipal Employees (AFSCME)"])


def test_compound_side_against_a_union_still_gives_both_roles() -> None:
    employer, union = assign_roles(
        "Lane County",
        "Lane County Peace Officers Assn and Lane County Sheriff",
    )
    assert employer == "Lane County; Lane County Sheriff"
    assert union == "Lane County Peace Officers Assn"


def test_all_public_compound_is_kept_whole() -> None:
    employer, union = assign_roles(
        "Polk County Deputy Sheriff's Association",
        "Polk County, Polk County Board of Commissioners, and Polk County Sheriff",
    )
    assert employer == (
        "Polk County, Polk County Board of Commissioners, and Polk County Sheriff"
    )
    assert union == "Polk County Deputy Sheriff's Association"


# --- individuals ---------------------------------------------------------


def test_individuals_are_recognised() -> None:
    for name in ("S. R.", "L.H.", "R. B.", "W.M.", "Chartier", "Trots", "Lopez",
                 "Gault", "Jepson", "Jane Doe", "John Q. Smith"):
        assert is_personal_name(name), name


def test_individual_against_each_kind_of_party() -> None:
    assert assign_roles("Chartier", "SEIU Local 503") == ("", "SEIU Local 503")
    assert assign_roles("Lopez", "City of Salem") == ("City of Salem", "")


def test_unclassifiable_side_still_releases_the_union() -> None:
    # Not a public body, not a union, not a personal name — the union on the
    # other side is still proven.
    assert assign_roles("Zorba Enterprises Widget Team", "AFSCME Local 88") == (
        "",
        "AFSCME Local 88",
    )


def test_one_party_captions_stay_empty() -> None:
    assert assign_roles("In the Matter of the Petition of Lane County", "") == ("", "")
    assert assign_roles("", "In the Matter of AFSCME Local 88") == ("", "")


# --- a side that is itself a union is never split --------------------------


def test_a_union_with_and_in_its_own_name_is_not_split() -> None:
    employer, union = assign_roles(
        "State College and University Professional Association, PSEA/NEA",
        "Pennsylvania State System of Higher Education",
    )
    assert union == "State College and University Professional Association, PSEA/NEA"
    assert employer != "State College and University Professional Association, PSEA/NEA"
    assert "State College" not in employer

    employer, union = assign_roles(
        "Association of Pennsylvania State College and University Faculties",
        "Pennsylvania State System of Higher Education",
    )
    assert union == "Association of Pennsylvania State College and University Faculties"
    assert "University Faculties" not in employer
    assert has_union_head(
        "Association of Pennsylvania State College and University Faculties"
    )


def test_legitimate_compounds_still_split_alongside_the_union_guard() -> None:
    assert assign_roles("Multnomah County and AFSCME Local 88", "Jepson") == (
        "Multnomah County",
        "AFSCME Local 88",
    )
    assert assign_roles(
        "City of Medford and Teamsters Local 223",
        "In the Matter of a Petition",
    ) == ("City of Medford", "Teamsters Local 223")
    assert assign_roles(
        "Salem Education Association and Salem School District 24J", "X"
    ) == ("Salem School District 24J", "Salem Education Association")
    assert assign_roles(
        "Bay Area Hospital and Oregon Licensed Practical Nurses Association", "X"
    ) == ("Bay Area Hospital", "Oregon Licensed Practical Nurses Association")
    employer, union = assign_roles(
        "Portland Firefighters' Association, Local 43 and City of Portland "
        "Fire and Rescue Bureau",
        "X",
    )
    assert employer == "City of Portland Fire and Rescue Bureau"
    assert union == "Portland Firefighters' Association, Local 43"


# --- "Union" as a place adjective, not the organisation noun ---------------


def test_union_as_place_adjective_is_not_a_union_token() -> None:
    for name in (
        "Union High School District 5",
        "Union County",
        "Union School District",
        "Union Township",
        "Union City",
    ):
        assert not is_union(name), name
        assert is_public_employer(name), name

    for name in (
        "Teamsters Union",
        "Oregon Public Employees Union",
        "Union of Operating Engineers",
        "Union Local 371",
    ):
        assert is_union(name), name


def test_union_prefixed_public_body_in_a_compound_caption() -> None:
    employer, union = assign_roles(
        "Union High School District 5 and Clackamas County",
        "Oregon School Employees Association",
    )
    assert "Union High School District 5" not in union
    assert union == "Oregon School Employees Association"


# --- OR ERB residuals, 2026-09-29: every caption below is a real index row --


def test_a_municipal_body_opens_a_compound_even_when_a_union_acronym_closes_it() -> None:
    # The trailing "(IBEW)" is the second party's, not the whole side's.
    assert split_side(
        "City of Ashland and International Brotherhood of Electrical Workers, "
        "Local 659 (IBEW)"
    ) == (
        ["City of Ashland"],
        ["International Brotherhood of Electrical Workers, Local 659 (IBEW)"],
    )
    assert split_side(
        "Lane County and Administrative Professional Association of Lane County"
    ) == (["Lane County"], ["Administrative Professional Association of Lane County"])
    # Still one union: "State College" is not a municipal body.
    assert split_side(
        "State College and University Professional Association, PSEA/NEA"
    ) == ([], ["State College and University Professional Association, PSEA/NEA"])


def test_two_unions_in_one_caption_name_no_union() -> None:
    # A unit clarification or a raid: which union represents the unit is the
    # outcome, and the caption does not state it.
    assert assign_roles(
        "Ashland Police Association",
        "City of Ashland and International Brotherhood of Electrical Workers, "
        "Local 659 (IBEW)",
    ) == ("City of Ashland", "")
    assert assign_roles(
        "Gresham Police Officers' Association",
        "City of Gresham and Teamsters Local 223",
    ) == ("City of Gresham", "")


def test_the_same_union_named_twice_is_one_union() -> None:
    assert distinct_parties(
        [
            "Monroe Elementary Education Association",
            "Monroe Elementary Education Association, Sexton, Gellert",
        ]
    ) == ["Monroe Elementary Education Association"]
    assert distinct_parties(["Teamsters 670", "Teamsters 670"]) == ["Teamsters 670"]
    assert distinct_parties(["AFSCME Local 88", "AFSCME Local 881"]) == [
        "AFSCME Local 88",
        "AFSCME Local 881",
    ]


def test_an_individual_co_filing_with_the_union_is_dropped() -> None:
    assert assign_roles(
        "Mt. Hood Community College Faculty Association and Kotulski",
        "Mt. Hood Community College",
    ) == ("Mt. Hood Community College", "Mt. Hood Community College Faculty Association")
    assert split_side("Miller and Gresham Grade Teachers Association") == (
        [],
        ["Gresham Grade Teachers Association"],
    )
    # A word that opens a union's own name is not a co-filer.
    for name in (
        "Construction and General Laborers' Union Local 320",
        "Plumbers and Steamfitters Local 290",
        "Professional and Technical Employees, Local 17",
        "Building and Construction Trades Council of Pittsburgh, AFL-CIO",
    ):
        assert split_side(name) == ([], [name]), name


def test_a_procedural_label_is_not_part_of_the_party() -> None:
    assert assign_roles(
        "C.B.",
        "Linn County Sheriff's Office (LCSO) and Linn County Deputy Sheriff's "
        "Association (LCDSA) - Intervenor",
    ) == (
        "Linn County Sheriff's Office (LCSO)",
        "Linn County Deputy Sheriff's Association (LCDSA)",
    )


def test_a_union_and_a_county_joined_by_a_hyphen() -> None:
    assert assign_roles(
        "Hadley-Cordes-Burton-McMenamy",
        "Multnomah County Deputy Sheriffs Association-Multnomah County",
    ) == ("Multnomah County", "Multnomah County Deputy Sheriffs Association")
    # A hyphen inside one name is left alone.
    assert split_side("Salem-Keizer School District 24J") == (
        ["Salem-Keizer School District 24J"],
        [],
    )


def test_oregon_place_names_that_carry_union_words() -> None:
    assert assign_roles(
        "City of Union",
        "Laborers' International Union of North American (LiUNA) Local 121",
    ) == ("City of Union", "Laborers' International Union of North American (LiUNA) Local 121")
    assert is_public_employer("Klamath Union-Mazama High School District No. 2")
    assert is_public_employer("Oak Lodge Water Services")
    assert is_public_employer("Mid-Columbia Council of Governments")
    assert is_union("IAM Woodworkers Lodge W-261")
    assert is_union("Fraternal Order of Police Lodge 7")


def test_oregon_union_vocabulary() -> None:
    for name in (
        "East County Bargaining Council",
        "United Academics of Oregon State University",
        "ATU Division 757",
    ):
        assert is_union(name), name
    assert assign_roles(
        "East County Bargaining Council", "David Douglas School District"
    ) == ("David Douglas School District", "East County Bargaining Council")


def test_a_semicolon_list_of_respondents_is_classified_entry_by_entry() -> None:
    assert assign_roles(
        "Moustachetti",
        "Fairview Training Center; AFSCME Local 1246; Department of Justice (DOJ); "
        "Oregon State Hospital (OSH)",
    ) == ("Department of Justice (DOJ); Oregon State Hospital (OSH)", "AFSCME Local 1246")
