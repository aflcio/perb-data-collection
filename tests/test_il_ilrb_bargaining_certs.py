"""Tests for Illinois ILRB certification PDF row healing (infra-38)."""

from __future__ import annotations

from perb_data_collection.collectors.il_ilrb_bargaining_certs import (
    _heal_shredded_fields,
    _jurisdiction_city,
)


def test_heal_recovers_date_from_union() -> None:
    certified, employer, union, party = _heal_shredded_fields(
        certified="",
        employer="Village of Hinsdale",
        union="International 8/2/2024 Association of Fire Fighters",
        party="20",
    )
    assert certified == "8/2/2024"
    assert employer == "Village of Hinsdale"
    assert "8/2/2024" not in union
    assert "Fire Fighters" in union
    assert party == ""


def test_heal_does_not_invent_truncated_year() -> None:
    certified, _employer, union, _party = _heal_shredded_fields(
        certified="",
        employer="City of Troy",
        union="IAFF 05/10/202 Local 123",
        party="",
    )
    assert certified == ""
    assert "05/10/202" in union


def test_jurisdiction_city_skips_shredded_employer() -> None:
    assert _jurisdiction_city("City of Venice Local") == "Venice"
    assert _jurisdiction_city("Declaration of Disinterest City of Troy") == ""
    assert _jurisdiction_city("Village of Hinsdale") == "Hinsdale"
