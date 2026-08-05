"""Tests for shared CSV / schema helpers."""

from __future__ import annotations

from pathlib import Path

from perb_data_collection.csv_io import write_wide_csv, write_wide_jsonl
from perb_data_collection.schema import CANONICAL_CASE_TYPES, map_native_case_type


def test_canonical_case_types_nonempty() -> None:
    assert "CERTIFICATION" in CANONICAL_CASE_TYPES
    assert map_native_case_type("RC", {"RC": "RECOGNITION"}) == "RECOGNITION"
    assert map_native_case_type("CERTIFICATION", {}) == "CERTIFICATION"


def test_write_wide_csv_and_jsonl(tmp_path: Path) -> None:
    rows = [
        {
            "row_key": "DC_PERB:1",
            "source_agency_code": "DC_PERB",
            "employer_name": "Agency",
        }
    ]
    fields = ["row_key", "source_agency_code", "employer_name"]
    csv_path = tmp_path / "out.csv"
    jsonl_path = tmp_path / "out.jsonl"
    assert write_wide_csv(rows, csv_path, fieldnames=fields) == 1
    assert write_wide_jsonl(rows, jsonl_path, fieldnames=fields) == 1
    assert "DC_PERB" in csv_path.read_text()
    assert "Agency" in jsonl_path.read_text()
