# National Mediation Board — representation determinations

**Status:** `collector_shipped`
**Agency:** National Mediation Board (NMB), federal, Railway Labor Act.
**Collector slug (proposed):** `nmb-representation-determinations`
**Last researched:** 2026-09-03

---

## Why this agency is in scope

Every other collector in this repo is a state or territorial public-sector board. NMB is federal — but it is the *only* representation authority for airline and railroad carriers, which are excluded from the NLRA entirely. Neither the NLRB feeds nor any state PERB touches them. Without NMB there is no representation evidence for any US airline or railroad anywhere in the pipeline.

Scale is modest (roughly 1,500–2,500 rows across all years) but coverage is unique and the parse is trivial.

---

## Recommended primary (2026-09-03)

| Item | Value |
|------|-------|
| **URL** | `https://nmb.gov/NMB_Application/index.php/agency-determinations/` |
| **Year pages** | 29 — `1998-determinations/` … `2023-determinations/`, then `fy2024-`, `fy2025-`, `fy2026-determinations/` |
| **Format** | Plain HTML `<table>` per year page. No PDF parsing needed for the listing. |
| **Listing fields** | `Page Cite`, `Date`, `Case`, **`Carrier`**, **`Union`**, `Craft/Class`, `Disposition`, `{vol} NMB Number` |
| **PDF permalinks** | `wp-content/uploads/YYYY/MM/*.pdf` — one per row, linked from the `Page Cite` cell |
| **Search reachability** | curl OK from this host (200) |
| **PDF reachability** | curl OK |
| **Grain** | one row per determination (case × craft/class) |

### Measured row counts

| Year page | Rows |
|-----------|------|
| `1998-determinations` | 122 |
| `2010-determinations` | 68 |
| `2019-determinations` | 23 |
| `2023-determinations` | 24 |
| `fy2026-determinations` | 32 |

Volume tapers sharply after the early 2000s. Full-corpus estimate ~1,500–2,500 rows.

### Sample rows (verbatim)

```
10/02/24 | R-7634 (NMB File No. CR-7253) | TGS Cedar Port Railroad, LLC | BLET | Train and Engine Service Employees | Certification
10/09/24 | R-7659 (RD-7619) (CR-7251)    | Carrollton Railroad          | BLET | Locomotive Engineers              | Certification
11/01/24 | R-7642 (File No. CR-7252)     | United Airlines, Inc.        | IAM  | Fleet Technical Instructors       | Dismissal
10/07/22 | R-7594                        | Omni Air International, LLC  | TWU  | Dispatchers                       | Certification
```

---

## Connector shape (proposed)

1. Fetch the index page; discover year-page URLs by regex on `*-determinations`. **Do not hardcode the list** — the naming switched from `YYYY-` to `fyYYYY-` at FY2024 and will keep drifting.
2. For each year page, parse the first `<table>`; map header cells by name, not position.
3. Emit one wide row per data row.
4. Keep the row's PDF href as `source_url`.
5. Cadence: monthly, same block as the other shipped collectors.

### Header drift to normalize

| Variant seen | Years |
|--------------|-------|
| `Craft-Class` | 1998, 2010 |
| `Craft/Class` | 2019, 2023, FY2025, FY2026 |
| `25 NMB Number` … `53 NMB Number` | column name encodes the reporter volume; changes every year |

Match the volume column positionally as "last column" or by regex `^\d+ NMB Number$`, and normalize to `nmb_volume_number`.

### Schema mapping

| Core column | Source |
|-------------|--------|
| `row_key` | `NMB:{case}` (+ craft/class discriminator — one case number can yield several rows, see Carrollton above) |
| `source_agency_code` | `NMB` |
| `case_number` | `Case` (strip the parenthetical `RD-`/`CR-` cross-refs into an extra field) |
| `employer_name` | `Carrier` |
| `union_name` | `Union` |
| `canonical_case_type` | map from `Disposition` (see below) |
| `native_case_type` | `Disposition` verbatim |
| `jurisdiction_state` | **null** — see caveats |
| `source_page_url` | year page |
| `source_url` | row PDF href |

Agency extras: `craft_class`, `nmb_volume_number`, `page_cite`, `determination_date`, `fiscal_year`.

**Disposition → `canonical_case_type`:** `Certification` → `CERTIFICATION`; `Decertification` → `DECERTIFICATION`; `Dismissal` → leave the native value and map to the nearest type only where unambiguous. Do not force every disposition into the enum — `Findings Upon Investigation`, `Dismissal`, and single-carrier determinations have no clean equivalent.

---

## Caveats

1. **No employer address, anywhere in the listing.** Carrier name only. Same posture as `nyc-ocb-bargaining-units`: ship the wide rows, defer ACE, match to D&B DMI by name downstream. Do not invent an address to satisfy the ACE template.
2. **No `jurisdiction_state`.** Carriers are multi-state by nature — a railroad certification covers a system, not a site. Leaving it null is correct; do not guess from the carrier's HQ.
3. **One case → many rows.** Carrollton Railroad above is three rows under three case numbers for three crafts; other years reuse one case number across crafts. `row_key` must include the craft/class.
4. **`Union` is an acronym**, not a full name (`BLET`, `BMWED`, `AFA`, `IAM`, `TWU`). Occasionally it is an individual (`Robert J. Wilson (Individual)`) — RLA allows individuals as representatives. Keep verbatim; resolve acronyms downstream against the AFL affiliate registry.
5. **FY vs CY.** Pages from FY2024 on are fiscal years (Oct–Sep); earlier pages are labelled by calendar year but the first row is typically an October date, so they were already fiscal. Record `fiscal_year` from the page, not from the date.
6. **Python `urllib` fails TLS on `nmb.gov` from macOS** (`CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical`). `curl` and `requests`/`httpx` with certifi are fine. Verify on the worker before scheduling.

---

## Link research

| URL | Role | Result from this host | Notes |
|-----|------|----------------------|-------|
| `nmb.gov/NMB_Application/index.php/agency-determinations/` | **primary index** | 200 | 29 year-page links |
| `.../fy2025-determinations/` | year page | 200 | 55 `<tr>`, 58 PDF links |
| `.../wp-json/wp/v2/types` | WP REST | 401 `rest_not_logged_in` | REST is gated; HTML tables are the path |
| `nmb.gov/wp-json/...` | WP REST (alt root) | 404 | wrong root |
| `knowledgestore.nmb.gov` | document archive | 302 | not probed further; HTML tables already suffice |

WordPress site, but the REST API requires auth — **parse the HTML, do not chase the API** (unlike CA PERB, where the WP REST route was the win).

---

## Verdict

- **Better link found?** Yes — the year pages are structured tables carrying carrier + union + craft/class directly, so no PDF NLP is needed for representation evidence.
- **Build collector?** **Yes, scheduled.** Plain HTTP, no WAF, stable shape across 29 years.
- **Scope caveats:** RLA carriers only (airlines, railroads). Employer name without address. Modest row count, unique sector.

---

## Next

- [x] Implement `perb_data_collection/collectors/nmb_representation_determinations.py`
- [x] Add row to [registry.md](../registry.md)
- [x] FirstLogic side: thin re-export shim + wide/S3/BQ load; ACE deferred (no address)
