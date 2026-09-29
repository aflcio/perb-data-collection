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


# --- PF-R-25-56-W: docket line, representation type, exact sealed date -----
#
# Fixtures: the live 2026 year page and the order PDF's text layer.

from pathlib import Path  # noqa: E402

from perb_data_collection.collectors.pa_plrb_final_orders import (  # noqa: E402
    apply_document,
    parse_order_document,
    read_order_documents,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = "https://www.pa.gov/agencies/dli/programs-services/labor-management-relations/pennsylvania-labor-relations-board/plrb-final-orders/2026-plrb-final-orders"


def _rows_2026() -> list[dict[str, str]]:
    html = (FIXTURES / "pa_plrb_final_orders_2026.html").read_text()
    return parse_year_page(html, decision_year="2026", page_url=PAGE, scraped_at="2026-09-29T00:00:00+00:00")


def test_listing_docket_line_is_the_case_number_and_the_key_does_not_move() -> None:
    row = next(r for r in _rows_2026() if r["pdf_url"].endswith("pittsburgh-pf25-56.pdf"))
    assert row["docket_number"] == "PF-R-25-56-W"
    assert row["case_number"] == "PF-R-25-56-W"
    assert row["canonical_case_type"] == "CERTIFICATION"
    # The warehouse key stays on the filename token it has always used.
    assert row["row_key"] == "PA_PLRB:2026:pittsburgh-pf25-56:pittsburgh-pf25-56.pdf"


def test_pf_r_25_56_w_order_names_the_employer_petitioner_outcome_and_date() -> None:
    text = (FIXTURES / "pa_plrb_pf-r-25-56-w_final_order.txt").read_text()
    parsed = parse_order_document(text)
    assert parsed["docket_number"] == "PF-R-25-56-W"
    assert parsed["employer_name"] == "City Of Pittsburgh"
    assert parsed["petitioner"] == "Teamsters Local No. 205"
    assert parsed["order_disposition"] == "dismissed"
    assert (parsed["order_date"], parsed["order_date_precision"]) == ("2026-03-17", "day")
    assert parsed["order_date_raw"] == "seventeenth day of March, 2026"

    row = next(r for r in _rows_2026() if r["pdf_url"].endswith("pittsburgh-pf25-56.pdf"))
    out = apply_document(row, text, "text_layer")
    assert (out["employer_name"], out["union_name"]) == ("City Of Pittsburgh", "Teamsters Local No. 205")
    assert out["party_source"] == "document"


def test_unreadable_order_keeps_the_year_and_no_date() -> None:
    rows = _rows_2026()
    read_order_documents(rows, delay_seconds=0, fetch_pdf=lambda url, **_: (_ for _ in ()).throw(RuntimeError("x")))
    assert all(r["order_date"] == "" and r["decision_year"] == "2026" for r in rows)


def test_intermediate_unit_is_the_employer_and_psea_the_union() -> None:
    row = next(r for r in _rows_2026() if "rodriquez" in r["pdf_url"])
    assert row["employer_name"] == "Colonial Intermediate Unit 20"
    assert row["union_name"] == "Pennsylvania State Education Association"
