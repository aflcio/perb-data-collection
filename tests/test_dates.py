"""Dates read off documents keep their precision and refuse impossible years."""

from __future__ import annotations

from datetime import date

from perb_data_collection.dates import bounded, date_after, find_dates, year_only

TODAY = date(2026, 9, 29)


def test_spelled_ordinal_and_numeric_forms() -> None:
    text = (
        "DATE: June 29, 2026. ... this seventeenth day of March, 2026. ... "
        "ENTERED this 14th day of June, 2011 ... twenty-first day of May, 1999 ... 6/29/2026"
    )
    assert [h.iso for h in find_dates(text, today=TODAY)] == [
        "2026-06-29", "2026-03-17", "2011-06-14", "1999-05-21", "2026-06-29",
    ]
    assert all(h.precision == "day" for h in find_dates(text, today=TODAY))


def test_impossible_years_are_not_dates() -> None:
    # Typed years seen in the warehouse: WA PERC 3036, F-7 3021, BLAW 5003 and 1001.
    for text in ("June 3, 3036", "March 30, 3021", "May 1, 5003", "October 2, 1001"):
        assert find_dates(text, today=TODAY) == []
    assert not bounded(2028, today=TODAY)
    assert bounded(2027, today=TODAY)
    assert not bounded(1934, today=TODAY)


def test_year_only_is_a_year_never_a_january_first() -> None:
    hit = year_only("2026", today=TODAY)
    assert (hit.iso, hit.precision) == ("2026", "year")
    assert year_only("3036", today=TODAY) is None


def test_date_after_uses_the_closing_block() -> None:
    text = "By email dated June 15, 2026, ... June 18, 2026 ...\nIT IS SO ORDERED.\nDATE: June 29, 2026\n"
    assert date_after(text, (r"DATE\s*:",), window=60, today=TODAY).iso == "2026-06-29"
