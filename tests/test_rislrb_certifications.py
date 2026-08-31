"""Tests for Rhode Island RISLRB certification scrape parsing."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.collectors.rislrb_certifications import (
    _parse_certification_table,
    enrich_rows_from_certification_pdfs,
    jurisdiction_city_from_employer,
    parse_certification_caption,
    scrape_certifications,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_certification_table_fixture() -> None:
    html = (FIXTURES / "rislrb_certifications_page.html").read_text()
    rows = _parse_certification_table(
        html,
        category="Firefighters",
        page_url="http://rislrb.ri.gov/FireFighterCert.htm",
        scraped_at="2026-08-26T00:00:00+00:00",
    )
    assert len(rows) >= 5
    by_case = {row["case_number"]: row for row in rows}

    # Employer text is inside the anchor; must not fall back to href="…".
    barrington = by_case["EE-1792"]
    assert barrington["employer_name"] == "Barrington"
    assert "href=" not in barrington["employer_name"].lower()
    assert barrington["certification_pdf_url"].endswith("CertificationEE1792.pdf")
    assert barrington["jurisdiction_city"] == "Barrington"
    assert barrington["jurisdiction_state"] == "RI"
    assert barrington["row_key"] == "RI_RISLRB:EE-1792:Firefighters"

    albion = by_case["EE-3685"]
    assert "Albion" in albion["employer_name"]
    assert "Fire District" in albion["employer_name"]
    assert "Lincoln" in albion["employer_name"]
    assert albion["unit_description"] == ""
    assert "href=" not in albion["employer_name"].lower()
    # Place parenthetical on a fire district → Lincoln.
    assert albion["jurisdiction_city"] == "Lincoln"

    # Unit descriptors move to unit_description; place parentheticals stay.
    clerks = by_case["EE-3430"]
    assert clerks["employer_name"] == "Barrington"
    assert "Clerks" in clerks["unit_description"]
    assert clerks["jurisdiction_city"] == "Barrington"

    bristol = by_case["EE-3083A"]
    assert "Bristol" in bristol["employer_name"]
    assert "Clerical" in bristol["unit_description"]
    assert "Amended" in bristol["employer_name"]

    chopmist = by_case["EE-3716"]
    assert "Scituate" in chopmist["employer_name"]
    assert "Rescue" in chopmist["unit_description"]

    assert all("href=" not in row["employer_name"].lower() for row in rows)
    assert len({row["row_key"] for row in rows}) == len(rows)


def test_scrape_certifications_uses_fixture() -> None:
    html = (FIXTURES / "rislrb_certifications_page.html").read_text()

    def fake_fetch(url: str, **kwargs: object) -> str:
        return html

    rows = scrape_certifications(
        fetch_html=fake_fetch,
        delay_seconds=0,
        enrich_pdfs=False,
    )
    # Eight listing pages × fixture rows, but row_key dedupes across categories.
    assert len(rows) >= 5
    assert all(row["source_agency_code"] == "RI_RISLRB" for row in rows)
    assert all("href=" not in row["employer_name"].lower() for row in rows)
    assert len({row["row_key"] for row in rows}) == len(rows)


def test_parse_certification_caption_providence_fire() -> None:
    text = (FIXTURES / "rislrb_certification_ee1445_caption.txt").read_text()
    caption = parse_certification_caption(text)
    assert caption["employer_name"] == "City of Providence"
    assert "Fire Fighters" in caption["union_name"] or "Firefighters" in caption["union_name"]
    assert "799" in caption["union_name"]
    assert caption["jurisdiction_city"] == "Providence"
    assert "uniformed" in caption["unit_description"].lower()


def test_parse_certification_caption_tolerates_ocr_typos() -> None:
    text = (
        "In the MATER of City of Providence Employer -and- Local #799, International "
        "Association of Flre Fighters, AFL-CIO Petitioner by secret ballot of All "
        "uniformed members of the Fire Department other than the chlef."
    )
    caption = parse_certification_caption(text)
    assert caption["employer_name"] == "City of Providence"
    assert "799" in caption["union_name"]
    assert caption["jurisdiction_city"] == "Providence"


def test_jurisdiction_city_from_employer_patterns() -> None:
    assert jurisdiction_city_from_employer("City of Providence") == "Providence"
    assert jurisdiction_city_from_employer("Barrington") == "Barrington"
    assert jurisdiction_city_from_employer("Albion Fire District (Lincoln)") == "Lincoln"
    assert jurisdiction_city_from_employer("State of Rhode Island") == ""
    assert jurisdiction_city_from_employer("Providence School Department") == ""


def test_enrich_rows_from_certification_pdfs_soft_fail() -> None:
    rows = [
        {
            "employer_name": "Barrington",
            "union_name": "IAFF",
            "unit_description": "",
            "jurisdiction_city": "",
            "certification_pdf_url": "http://example.test/missing.pdf",
        }
    ]

    def boom(url: str, **kwargs: object) -> bytes:
        raise RuntimeError("network down")

    enrich_rows_from_certification_pdfs(rows, delay_seconds=0, fetch_pdf=boom)
    assert rows[0]["employer_name"] == "Barrington"
    assert rows[0]["jurisdiction_city"] == "Barrington"


def test_enrich_rows_merges_caption() -> None:
    caption_text = (FIXTURES / "rislrb_certification_ee1445_caption.txt").read_text()
    rows = [
        {
            "employer_name": "",
            "union_name": "IAFF",
            "unit_description": "",
            "jurisdiction_city": "",
            "certification_pdf_url": "http://example.test/CertificationEE1445.pdf",
        }
    ]

    def fake_pdf(url: str, **kwargs: object) -> bytes:
        return b"%PDF-fake"

    enrich_rows_from_certification_pdfs(
        rows,
        delay_seconds=0,
        fetch_pdf=fake_pdf,
        pdf_to_text=lambda _b: caption_text,
    )
    assert rows[0]["employer_name"] == "City of Providence"
    assert rows[0]["jurisdiction_city"] == "Providence"
    assert "799" in rows[0]["union_name"]
