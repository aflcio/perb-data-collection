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

## Parties and roles

`employer_name` / `union_name` are **decided by content**
(`perb_data_collection.party_roles`), never by which side of a `v.` a party
sits on. A collector that reads the document also lands the caption's own
labelled parties, each in its own column, so standing and role stay separate:

| Column | Meaning |
|--------|---------|
| `petitioner` | Caption party labelled Petitioner / Charging Party / Complainant / Appellant |
| `respondent` | Caption party labelled Respondent / Appellee / Labor Organization |
| `agency` | Caption party labelled Agency / Employer (DC) |
| `intervenor` | Caption party labelled Intervenor |
| `certified_representative` | The union named in the operative certification section only (DC) |
| `certification_result` | `representative_certified`, `no_representative`, `section_not_found`, `document_unreadable` (DC) |
| `union_name_source` / `party_source` | Which rule filled `union_name` / the party columns: `certification`, `caption`, `document`, `listing_roles`, `filename`, `title`, `contested_unresolved`, `no_representative` |

On a contested election the petitioner is not the winner (DC 12-RC-02 was
petitioned by one union and certified another), so a representative comes only
from the certification section. When that section cannot be read and the
caption names two labour organisations, `union_name` stays empty.

## Dates

A date read off a document travels with its precision and its raw text
(`perb_data_collection.dates`): `<name>_date` (ISO), `<name>_date_raw`,
`<name>_date_precision` (`day` / `month` / `year`) and, where several rules
could supply it, `<name>_date_source` (e.g. `order_block`, `date_line`,
`sealed_dated_mailed`, `stamp`). A listing that only says the year leaves the
date empty and keeps `decision_year`; it never becomes January 1. Years before
1935 or more than a year past the run date are refused, not landed.

`document_text_method` says how a document's text was obtained: `text_layer`,
`docx`, `ocr`, `ocr_unavailable` (a scan on a host without tesseract),
`unreadable`, or `fetch_failed`. A null downstream can then be told apart from a
document that said nothing.

## Election tallies

A tally is not a result. WERC's annual recertification PDFs are endpoint
tallies published before challenges close; `document_status = endpoint_tally`,
and the eligible population, ballots, yes, no, the challenged columns and
`meets_51pct_threshold` are separate facts. None of them is a certification.

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
