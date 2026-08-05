"""Shared wide-row column conventions and canonical case-type enum."""

from __future__ import annotations

from collections.abc import Mapping

CANONICAL_CASE_TYPES = frozenset(
    {
        "CERTIFICATION",
        "DECERTIFICATION",
        "UNIT_CLARIFICATION",
        "UNIT_MODIFICATION",
        "AMENDMENT_OF_CERTIFICATION",
        "RECOGNITION",
        "ULP",
        "NEGOTIABILITY",
        "IMPASSE",
        "ARBITRATION",
        "FACT_FINDING",
        "SEVERANCE",
    }
)

# Columns every collector should populate when the source provides them.
CORE_WIDE_COLUMNS: tuple[str, ...] = (
    "row_key",
    "source_agency_code",
    "case_number",
    "canonical_case_type",
    "native_case_type",
    "employer_name",
    "union_name",
    "jurisdiction_city",
    "jurisdiction_state",
    "employer_street",
    "employer_zip",
    "source_page_url",
    "source_url",
    "scraped_at",
)


def map_native_case_type(native_code: str, mapping: Mapping[str, str]) -> str:
    """Map a native agency code into CANONICAL_CASE_TYPES when possible."""
    key = native_code.strip().upper()
    if key in CANONICAL_CASE_TYPES:
        return key
    return mapping.get(key, key)
