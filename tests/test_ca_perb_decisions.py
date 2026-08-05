"""Tests for CA PERB Decision Bank REST parsing."""

from __future__ import annotations

import json
from pathlib import Path

from perb_data_collection.collectors.ca_perb_decisions import (
    parse_api_page,
    parse_decision_post,
    scrape_decisions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_posts() -> list[dict]:
    return json.loads((FIXTURES / "ca_perb_decisions_api.json").read_text())


def test_parse_api_page_fixture() -> None:
    posts = _fixture_posts()
    rows = parse_api_page(posts, scraped_at="2026-07-19T00:00:00+00:00")
    assert len(rows) == len(posts)
    assert all(r["source_agency_code"] == "CA_PERB" for r in rows)
    assert all(r["jurisdiction_state"] == "CA" for r in rows)
    row_e = next(r for r in rows if r["decision_number"].upper() == "3032E")
    assert row_e["jurisdiction_statute"] == "EERA"
    assert "Santa Monica" in row_e["employer_name"]
    assert row_e["canonical_case_type"] == "DECERTIFICATION"
    row_s = next(r for r in rows if r["decision_number"].upper() == "3027S")
    assert row_s["jurisdiction_statute"] == "DILLS"
    assert "California" in row_s["employer_name"] or "Corrections" in row_s["employer_name"]
    row_m = next(r for r in rows if r["decision_number"].upper() == "3040M")
    assert row_m["jurisdiction_statute"] == "MMBA"
    assert row_m["canonical_case_type"] == "ULP"
    assert "AFSCME" in row_m["union_name"] or "Federation" in row_m["union_name"]


def test_parse_alj_decision_number() -> None:
    post = {
        "id": 1,
        "slug": "a537h",
        "title": {"rendered": "A537H"},
        "content": {
            "rendered": (
                "<p><strong>Description:</strong> Interested Party University Professional "
                "and Technical Employees sought to appeal a determination involving "
                "Respondent Regents of the University of California violated nothing.</p>"
                "<p><strong>Disposition:</strong> Denied.</p>"
            )
        },
        "date": "2025-01-01T00:00:00",
        "link": "https://perb.ca.gov/decision/a537h/",
    }
    row = parse_decision_post(post, scraped_at="2026-07-19T00:00:00+00:00")
    assert row is not None
    assert row["decision_number"] == "A537H"
    assert row["native_case_type"] == "ALJ_APPEAL"
    assert row["jurisdiction_statute"] == "HEERA"


def test_scrape_decisions_with_fixture() -> None:
    posts = _fixture_posts()
    payload = json.dumps(posts)

    def fake_fetch(url: str, **kwargs: object) -> str:
        if "page=1" in url:
            return payload
        return "[]"

    rows = scrape_decisions(fetch_json=fake_fetch, delay_seconds=0)
    assert len(rows) == len(posts)
    assert all(r["wp_post_id"] for r in rows)
