# Wide-row schema

Collectors write **one wide CSV** (or JSONL via the library). Agency-native
extras are allowed. Prefer these shared core columns when the source provides
them.

## Core columns

| Column | Meaning |
|--------|---------|
| `row_key` | Stable unique id, usually `{AGENCY_CODE}:{native_id}` |
| `source_agency_code` | Short agency code (e.g. `DC_PERB`) |
| `case_number` | Agency case / docket number when present |
| `canonical_case_type` | Value from the enum below |
| `native_case_type` | Agency's own type label/code |
| `employer_name` | Employer / agency / respondent |
| `union_name` | Union / employee organization |
| `jurisdiction_city` | City or locality when known |
| `jurisdiction_state` | Two-letter postal code |
| `employer_street` | Street address when published |
| `employer_zip` | ZIP when published |
| `source_page_url` | Listing / search page used |
| `source_url` | Best permalink (PDF, case page, API item) |
| `scraped_at` | ISO-8601 UTC timestamp of the collect run |

Agency extras (examples): `certification_number`, `dc_register_cite`,
`decision_number`, `document_title`, `wp_post_id`.

## Canonical case types

```
CERTIFICATION
DECERTIFICATION
UNIT_CLARIFICATION
UNIT_MODIFICATION
AMENDMENT_OF_CERTIFICATION
RECOGNITION
ULP
NEGOTIABILITY
IMPASSE
ARBITRATION
FACT_FINDING
SEVERANCE
```

Defined in `perb_data_collection.schema.CANONICAL_CASE_TYPES`.

## Column lists

Per-collector field orders live as `WIDE_FIELDNAMES` on each collector module
under `src/perb_data_collection/collectors/`.
