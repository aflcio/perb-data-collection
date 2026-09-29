"""Tests for Delaware PERB year-indexed decision scrape parsing."""

from __future__ import annotations

import re
from pathlib import Path

from perb_data_collection.collectors.de_perb_decisions import (
    list_year_pages,
    parse_year_page,
    scrape_decisions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_list_year_pages() -> None:
    html = (FIXTURES / "de_perb_decisions_index.html").read_text()
    years = list_year_pages(html)
    assert years
    assert years[0][0] >= years[-1][0]


def test_parse_year_page_fixture() -> None:
    html = (FIXTURES / "de_perb_decisions_2026.html").read_text()
    rows = parse_year_page(
        html,
        decision_year="2026",
        page_url="https://perb.delaware.gov/2026-decisions/",
        scraped_at="2026-07-14T00:00:00+00:00",
    )
    assert len(rows) >= 3
    assert rows[0]["jurisdiction_state"] == "DE"
    assert rows[0]["pdf_url"].endswith(".pdf")
    assert rows[0]["case_number"]
    # Decision-type labels must not land in employer or city.
    assert all(
        not re.search(
            r"(?i)Order of Dismissal|Probable Cause|Unfair Labor Practice",
            row["employer_name"] or "",
        )
        for row in rows
    )
    assert all(row["jurisdiction_city"] == "" or "Decision" not in row["jurisdiction_city"] for row in rows)
    # -v- filenames yield a real party on at least one side.
    v_rows = [row for row in rows if "-v-" in row["pdf_url"].lower() or "-v." in row["pdf_url"].lower()]
    assert v_rows
    assert any(row["employer_name"] or row["union_name"] for row in v_rows)


def test_parties_from_legacy_filename() -> None:
    from perb_data_collection.collectors.de_perb_decisions import _parties_from_filename

    emp, union = _parties_from_filename(
        "1984-1-11-84-3-DS-Capital-Educators-Assn.pdf"
    )
    assert emp == ""
    assert "Capital Educators" in union

    emp, union = _parties_from_filename(
        "1984-1-3-84-1-1-DS-Seaford-School-Board.pdf"
    )
    assert "Seaford School Board" in emp
    assert union == ""


def test_scrape_decisions_with_fixtures() -> None:
    index = (FIXTURES / "de_perb_decisions_index.html").read_text()
    year = (FIXTURES / "de_perb_decisions_2026.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        if "2026" in url:
            return year
        if url.rstrip("/").endswith("decisions"):
            return index
        return "<html></html>"

    rows = scrape_decisions(fetch_html=fake_fetch, read_documents=False)
    assert len(rows) >= 3
    assert all(
        not re.search(r"(?i)Probable Cause Determination", row["jurisdiction_city"] or "")
        for row in rows
    )


# --- the decision document decides roles and date (case 1546 and friends) ---
#
# Fixtures are the real PDFs' text layers (pdftotext, reading order).

from perb_data_collection.collectors.de_perb_decisions import (  # noqa: E402
    apply_document,
    parse_decision_document,
    read_decision_documents,
)


def test_1546_employer_charged_the_union_and_the_order_is_dated_june_29() -> None:
    text = (FIXTURES / "de_perb_1546_order_of_dismissal.txt").read_text()
    out = parse_decision_document(text)
    assert out["petitioner"].startswith("DEPARTMENT OF SERVICES FOR CHILDREN")
    assert out["respondent"].startswith("DELAWARE STATE AND FEDERAL EMPLOYEES LOCAL 1029")
    assert out["employer_name"] == "DEPARTMENT OF SERVICES FOR CHILDREN, YOUTH, AND THEIR FAMILIES"
    assert "LOCAL 1029" in out["union_name"] and "LABORERS" in out["union_name"]
    assert (out["order_date"], out["order_date_precision"]) == ("2026-06-29", "day")
    assert out["order_date_raw"] == "June 29, 2026"


def test_1427_union_charged_the_employer_same_parties_opposite_sides() -> None:
    text = (FIXTURES / "de_perb_1427_decision.txt").read_text()
    out = parse_decision_document(text)
    assert out["petitioner"].startswith("DELAWARE STATE AND FEDERAL EMPLOYEES LOCAL 1029")
    assert out["employer_name"].startswith("DEPARTMENT OF SERVICES FOR CHILDREN")
    assert "LOCAL 1029" in out["union_name"]
    assert out["order_date"] == "2026-01-29"


def test_individual_appellant_is_neither_party_column() -> None:
    text = (FIXTURES / "de_perb_1494a_board_review.txt").read_text()
    out = parse_decision_document(text)
    assert out["petitioner"] == "TIARA CAMPBELL-SUBER"
    assert out["employer_name"] == ""
    assert out["union_name"] == "AFSCME LOCAL 1102"
    assert out["order_date"] == "2026-03-23"


def test_filename_fallback_never_assigns_roles_by_position() -> None:
    from perb_data_collection.collectors.de_perb_decisions import _parties_from_filename

    # "DSCYF" proves nothing, so it is not filed as a union for being on the left.
    assert _parties_from_filename("1546-ULP-Order-of-Dismissal-DSCYF-v-LiUNA-website.pdf") == ("", "LiUNA")
    assert _parties_from_filename("1427-Dec-OOD-LiUNA-1029-v-DSCYF-1-29-26-website.pdf") == ("", "LiUNA 1029")
    # A hyphen segment beginning with "V" is not a versus.
    employer, union = _parties_from_filename("1600-Smyrna-Vo-Tech-Educators-Assn.pdf")
    assert (employer, union) == ("", "Smyrna Vo Tech Educators Assn")


def test_unreadable_document_keeps_the_year_and_no_invented_date() -> None:
    html = (FIXTURES / "de_perb_decisions_2026.html").read_text()
    rows = parse_year_page(
        html,
        decision_year="2026",
        page_url="https://perb.delaware.gov/2026-decisions/",
        scraped_at="2026-09-29T00:00:00+00:00",
    )
    counts = read_decision_documents(
        rows,
        delay_seconds=0,
        fetch_pdf=lambda url, **_: (_ for _ in ()).throw(RuntimeError("WAF page")),
    )
    assert counts == {"fetch_failed:undated": len(rows)}
    assert all(r["order_date"] == "" and r["decision_year"] == "2026" for r in rows)
    assert all(r["document_text_method"] == "fetch_failed" for r in rows)


def test_apply_document_marks_caption_as_the_party_source() -> None:
    text = (FIXTURES / "de_perb_1546_order_of_dismissal.txt").read_text()
    row = {"employer_name": "LiUNA", "union_name": "DSCYF", "jurisdiction_city": "LiUNA"}
    out = apply_document(row, text, "text_layer")
    assert out["party_source"] == "caption"
    assert out["union_name"] != "DSCYF"
    assert out["jurisdiction_city"] != "LiUNA"
