"""PA PLRB final orders: complainant-v-respondent captions do not fix roles."""

from __future__ import annotations

from perb_data_collection.collectors.pa_plrb_final_orders import (
    _parties_from_title,
    parse_year_page,
)

_HTML = """
<ul>
  <li><a href="/content/dam/copapwp-pagov/final-orders/donegal-twp-pera-c-24-101-w.pdf">
      Donegal Township v. International Union of Operating Engineers, Local 66</a></li>
  <li><a href="/content/dam/copapwp-pagov/final-orders/psea-pera-c-24-102-e.pdf">
      Jane Doe v. Pennsylvania State Education Association</a></li>
  <li><a href="/content/dam/copapwp-pagov/final-orders/afscme-pera-c-24-103-e.pdf">
      AFSCME District Council 89, Local 2026 v. Borough of Ambler</a></li>
</ul>
"""


def test_employer_filed_charge_does_not_file_the_township_as_a_union() -> None:
    employer, union = _parties_from_title(
        "Donegal Township v. International Union of Operating Engineers, Local 66"
    )
    assert employer == "Donegal Township"
    assert "Local 66" in union


def test_duty_of_fair_representation_charge_leaves_employer_empty() -> None:
    employer, union = _parties_from_title(
        "Jane Doe v. Pennsylvania State Education Association"
    )
    assert employer == ""
    assert union == "Pennsylvania State Education Association"


def test_parse_year_page_keeps_the_title_and_empties_unproven_columns() -> None:
    rows = parse_year_page(
        _HTML,
        decision_year="2024",
        page_url="https://www.pa.gov/x/2024-plrb-final-orders",
        scraped_at="2026-09-10T00:00:00+00:00",
    )
    by_title = {row["document_title"]: row for row in rows}
    assert len(rows) == 3

    donegal = by_title[
        "Donegal Township v. International Union of Operating Engineers, Local 66"
    ]
    assert donegal["employer_name"] == "Donegal Township"
    assert "Local 66" in donegal["union_name"]
    assert donegal["jurisdiction_city"] == "Donegal Township"

    dfr = by_title["Jane Doe v. Pennsylvania State Education Association"]
    assert dfr["employer_name"] == ""
    assert dfr["union_name"] == "Pennsylvania State Education Association"
    assert dfr["jurisdiction_city"] == ""
    # nothing is lost: the caption survives verbatim
    assert dfr["document_title"] == "Jane Doe v. Pennsylvania State Education Association"

    union_filed = by_title["AFSCME District Council 89, Local 2026 v. Borough of Ambler"]
    assert union_filed["employer_name"] == "Borough of Ambler"
    assert union_filed["union_name"].startswith("AFSCME")
