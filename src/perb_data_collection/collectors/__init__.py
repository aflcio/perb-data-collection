"""Agency collectors and CLI registry."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from perb_data_collection.collectors import (
    ak_alra_board_decisions,
    ca_perb_decisions,
    dc_perb_certifications,
    de_perb_decisions,
    fl_perc_certifications,
    hi_hlrb_employee_orgs,
    ia_eab_unit_certifications,
    il_ilrb_bargaining_certs,
    ks_peera_unit_rosters,
    md_perb_election_certs,
    me_mlrb_unit_rep_cases,
    mn_bms_certifications,
    nmb_representation_determinations,
    ne_cir_reporter,
    nh_pelrb_certifications,
    nj_perc_issued_decisions,
    nm_pelrb_bargaining_units,
    nv_emrb_employer_directory,
    nyc_ocb_bargaining_units,
    or_erb_contentdm_orders,
    pa_plrb_final_orders,
    rislrb_certifications,
    vt_vlrb_volume_decisions,
    wa_perc_certifications,
    werc_election_results,
)

CollectFn = Callable[..., int]

COLLECTORS: dict[str, dict[str, Any]] = {
    "ak-alra-board-decisions": {
        "description": "Alaska ALRA board decision PDFs",
        "csv_name": "ak_alra_board_decisions.csv",
        "collect": ak_alra_board_decisions.scrape_to_wide_csv,
        "module": ak_alra_board_decisions,
    },
    "ca-perb-decisions": {
        "description": "California PERB Decision Bank (WP REST)",
        "csv_name": "ca_perb_decisions.csv",
        "collect": ca_perb_decisions.scrape_to_wide_csv,
        "module": ca_perb_decisions,
    },
    "dc-perb-certifications": {
        "description": "DC PERB certification index",
        "csv_name": "dc_perb_certifications.csv",
        "collect": dc_perb_certifications.scrape_to_wide_csv,
        "module": dc_perb_certifications,
    },
    "de-perb-decisions": {
        "description": "Delaware PERB year-indexed decisions",
        "csv_name": "de_perb_decisions.csv",
        "collect": de_perb_decisions.scrape_to_wide_csv,
        "module": de_perb_decisions,
    },
    "fl-perc-certifications": {
        "description": "Florida PERC certifications (often egress-limited)",
        "csv_name": "fl_perc_certifications.csv",
        "collect": fl_perc_certifications.scrape_to_wide_csv,
        "module": fl_perc_certifications,
    },
    "hi-hlrb-employee-orgs": {
        "description": "Hawaii HLRB employee-organization PDF roster",
        "csv_name": "hi_hlrb_employee_orgs.csv",
        "collect": hi_hlrb_employee_orgs.scrape_to_wide_csv,
        "module": hi_hlrb_employee_orgs,
    },
    "ia-eab-unit-certifications": {
        "description": "Iowa EAB unit certifications",
        "csv_name": "ia_eab_unit_certifications.csv",
        "collect": ia_eab_unit_certifications.scrape_to_wide_csv,
        "module": ia_eab_unit_certifications,
    },
    "il-ilrb-bargaining-certs": {
        "description": "Illinois ILRB bargaining-unit certification PDFs",
        "csv_name": "il_ilrb_bargaining_certs.csv",
        "collect": il_ilrb_bargaining_certs.scrape_to_wide_csv,
        "module": il_ilrb_bargaining_certs,
    },
    "ks-peera-unit-rosters": {
        "description": "Kansas PEERA unit rosters (Playwright fallback)",
        "csv_name": "ks_peera_unit_rosters.csv",
        "collect": ks_peera_unit_rosters.scrape_to_wide_csv,
        "module": ks_peera_unit_rosters,
    },
    "md-perb-election-certs": {
        "description": "Maryland PERB election certifications",
        "csv_name": "md_perb_election_certs.csv",
        "collect": md_perb_election_certs.scrape_to_wide_csv,
        "module": md_perb_election_certs,
    },
    "me-mlrb-unit-rep-cases": {
        "description": "Maine MLRB unit/representation cases",
        "csv_name": "me_mlrb_unit_rep_cases.csv",
        "collect": me_mlrb_unit_rep_cases.scrape_to_wide_csv,
        "module": me_mlrb_unit_rep_cases,
    },
    "mn-bms-certifications": {
        "description": "Minnesota BMS certifications (harvest JSONL ingest)",
        "csv_name": "mn_bms_certifications.csv",
        "collect": mn_bms_certifications.scrape_to_wide_csv,
        "module": mn_bms_certifications,
        "needs_harvest": True,
    },
    "nmb-representation-determinations": {
        "description": "National Mediation Board representation determinations",
        "csv_name": "nmb_representation_determinations.csv",
        "collect": nmb_representation_determinations.scrape_to_wide_csv,
        "module": nmb_representation_determinations,
    },
    "ne-cir-reporter": {
        "description": "Nebraska CIR Reporter decisions",
        "csv_name": "ne_cir_reporter.csv",
        "collect": ne_cir_reporter.scrape_to_wide_csv,
        "module": ne_cir_reporter,
    },
    "nh-pelrb-certifications": {
        "description": "New Hampshire PELRB certifications (harvest TSV ingest)",
        "csv_name": "nh_pelrb_certifications.csv",
        "collect": nh_pelrb_certifications.scrape_to_wide_csv,
        "module": nh_pelrb_certifications,
        "needs_harvest": True,
    },
    "nj-perc-issued-decisions": {
        "description": "New Jersey PERC Issued Decisions (Domino XML)",
        "csv_name": "nj_perc_issued_decisions.csv",
        "collect": nj_perc_issued_decisions.scrape_to_wide_csv,
        "module": nj_perc_issued_decisions,
    },
    "nm-pelrb-bargaining-units": {
        "description": "New Mexico PELRB bargaining units PDF",
        "csv_name": "nm_pelrb_bargaining_units.csv",
        "collect": nm_pelrb_bargaining_units.scrape_to_wide_csv,
        "module": nm_pelrb_bargaining_units,
    },
    "nv-emrb-employer-directory": {
        "description": "Nevada EMRB employer directory PDF",
        "csv_name": "nv_emrb_employer_directory.csv",
        "collect": nv_emrb_employer_directory.scrape_to_wide_csv,
        "module": nv_emrb_employer_directory,
    },
    "nyc-ocb-bargaining-units": {
        "description": "NYC OCB bargaining units roster",
        "csv_name": "nyc_ocb_bargaining_units.csv",
        "collect": nyc_ocb_bargaining_units.scrape_to_wide_csv,
        "module": nyc_ocb_bargaining_units,
    },
    "or-erb-contentdm-orders": {
        "description": "Oregon ERB ContentDM final orders",
        "csv_name": "or_erb_contentdm_orders.csv",
        "collect": or_erb_contentdm_orders.scrape_to_wide_csv,
        "module": or_erb_contentdm_orders,
    },
    "pa-plrb-final-orders": {
        "description": "Pennsylvania PLRB final orders",
        "csv_name": "pa_plrb_final_orders.csv",
        "collect": pa_plrb_final_orders.scrape_to_wide_csv,
        "module": pa_plrb_final_orders,
    },
    "rislrb-certifications": {
        "description": "Rhode Island RISLRB certifications",
        "csv_name": "rislrb_certifications.csv",
        "collect": rislrb_certifications.scrape_to_wide_csv,
        "module": rislrb_certifications,
    },
    "vt-vlrb-volume-decisions": {
        "description": "Vermont VLRB volume decision ZIP indexes",
        "csv_name": "vt_vlrb_volume_decisions.csv",
        "collect": vt_vlrb_volume_decisions.scrape_to_wide_csv,
        "module": vt_vlrb_volume_decisions,
    },
    "wa-perc-certifications": {
        "description": "Washington PERC pending representation",
        "csv_name": "wa_perc_certifications.csv",
        "collect": wa_perc_certifications.scrape_to_wide_csv,
        "module": wa_perc_certifications,
    },
    "werc-election-results": {
        "description": "Wisconsin WERC election results PDFs",
        "csv_name": "werc_election_results.csv",
        "collect": werc_election_results.scrape_to_wide_csv,
        "module": werc_election_results,
    },
}


def collect(slug: str, out_dir: Path, *, harvest_path: Path | None = None) -> tuple[Path, int]:
    """Run a collector by slug into out_dir; return (csv_path, row_count)."""
    key = slug.strip().lower().replace("_", "-")
    if key not in COLLECTORS:
        raise KeyError(f"Unknown collector slug: {slug}")
    meta = COLLECTORS[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / meta["csv_name"]
    kwargs: dict[str, Any] = {}
    if harvest_path is not None:
        kwargs["harvest_path"] = harvest_path
    count = meta["collect"](csv_path, **kwargs)
    return csv_path, count
