# National Mediation Board — representation determinations

**Status:** `collector_shipped`
**Agency:** National Mediation Board (NMB), federal, Railway Labor Act.
**Collector slug (proposed):** `nmb-representation-determinations`
**Last researched:** 2026-09-10

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

### Disposition inventory (measured 2026-09-10)

Counts are from parsing four year pages. The column is free text typed by hand
each year — it is *not* an enum, and near-duplicates (spacing, en dash vs
hyphen, ALL CAPS, `FUI` vs `Findings Upon Investigation`, one typo
`single transportation syste`) are common. Classify by pattern, never by
equality against a fixed list.

| Disposition (verbatim) | FY2025 | 2013 | 2004 | 1998 | Certification? |
|---|---|---|---|---|---|
| `Certification` | 24 | 17 | 23 | 44 | yes |
| `Certification – TWU` / `– IAM` / `– IBT` / `– ALPA` / `– AMFA` | – | 1 | 2 | 4 | yes |
| `Investigation- Certification Determination` | 1 | – | – | – | yes |
| `Findings Upon Investigation – Certification Determination` | 1 | – | – | – | yes |
| `Findings Upon Investigation- Certification Determination` | 1 | – | – | – | yes |
| `FUI – certification` / `FUI – Certification` / `FUI- Certification` | – | 3 | – | – | yes |
| `Dismissal` | 4 | 9 | 15 | 38 | no |
| `Dismissal- Withdrawn During Investigation` / `Dismissal – Withdrawn During Investigation` | 2 | – | – | – | no |
| `WDI – dismissal` / `WDI-dismissal` / `WDI – dismissal;` | – | 4 | 11 | – | no |
| `Dismissal – WDI` | – | – | – | 4 | no |
| `Dismissal- Insufficient Showing of Interest` / `Dismissal – ISI` / `FUI – dismissal (ISI)` | 1 | – | 1 | 1 | no |
| `FUI – dismissal` / `FUI – dismissal (not a single transportation system)` | – | 2 | 5 | – | no |
| `FINDINGS UPON INVESTIGATION – DISMISSAL` / `Findings Upon Investigation – Dismissal` | 2 | – | – | – | no |
| `Findings Upon Investigation` | 1 | – | – | 2 (`FUI`) | no |
| `Findings Upon Investigation – Authorization of Election` / `Findings Upon Investigation- Authorization of Election` / `FUI – authorization of election` / `FUI – Authorization of Election` / `FUI – election authorized` / `Election Auth.` | 2 | 2 | 1 | 4 | no |
| `Findings Upon Investigation – Single Carrier Determination` (4 casings) / `FUI – single transportation system` / `…syste` / `Single Carrier` / `Single Carrier – confirmed` / `Single Carrier confirmed` | 4 | 3 | 3 | 1 | no |
| `FUI – craft or class` / `FUI – craft and class determination` | – | 2 | 1 | – | no |
| `FUI – election not tainted` | – | – | 1 | – | no |
| `Transfer of Certification` / `Certification transferred` / `Certification Transferred` / `Cert. Transferred` | – | 23 | 27 | 1 | **no** — see caveat 8 |
| `Revocation of Certification` / `Cert-revoked` | 2 | 1 | 2 | 1 | no |
| `Jurisdictional Opinion` / `Re: Juris Opinion.` / `Jurisdiction – not subject to the RLA` / `RLA Jurisdiction – confirmed` / `RLA Jurisdiction – not confirmed` | 5 | 3 | 8 | 1 | no |
| `Appeal Denied` / `Eligibility Appeal – denied` / `Eligibility Appeal denied` / `BLET Eligibility Appeal – denied` / `Election Appeal denied` / `Eligibility Appeals – granted in part; Dismissal – ISI` | – | 2 | 8 | 3 | no |
| `Appeal Reversal` / `Sustained` / `Denied` / `Motion Denied` / `MFR Denied` / `MFR – relief denied` / `Recon Motion Denied` / `Reconsideration Motion Denied` / `Request for Pre-Election Relief – Denied` | 1 | – | 3 | 8 | no |
| `Ltr. Re: Eligibility` / `Ltr. Re. Eligibility` | – | – | – | 6 | no |
| `Election Re-run` | – | – | – | 2 | no |
| `Waiving Certain Time Limits` / `Changes to Board Procedures /Modified Voting Instructions` / `Maintenance of Way` / `Notice of Hearing re PEB #237` / `Submission Timely` | – | 5 | 1 | 1 | no |
| *(empty cell)* | 3 | – | – | – | no |

Row totals: FY2025 54, 2013 76, 2004 112, 1998 122.

Classification rule as implemented (`_is_certification_disposition`): the text
must contain a `certif*`/`cert` token **and** none of
`transfer`, `revocation`/`revoke`, `decert`, `dismiss`, `denied`/`deny`,
`withdraw`, `extinguish`, `not subject`, `not confirmed`, `re-run`/`rerun`.

**Disposition → `canonical_case_type`:** a certification disposition → `CERTIFICATION`; everything else (decertification, `Dismissal`, `Withdrawal`, revocation, transfer, jurisdiction, appeals) keeps the native value with an **empty** canonical type. Do not force every disposition into the enum. The same test drives the new `representation_asserted` column: `true` only for a certification disposition, `false` otherwise.

---

## The applicant is not the representative

The listing's `Union` column is the **applicant** — the organisation that
invoked the Board's services. It is not necessarily the union the Board
certified, and on a losing application it is the union that *failed*.

> `NMB:R-6952` — American Airlines, Flight Dispatchers, 12-2-03, 31 NMB No. 15.
> Listing `Union` = **PAFCA**. The election result printed in the
> determination is PAFCA 99, TWU 120, void 1, of 233 eligible, and the
> certification sentence names the incumbent **Transport Workers Union of
> America**. Landing the listing row as representation asserts the exact
> opposite of what happened.
>
> The disposition for that row is the giveaway: `Certification – TWU`. Some
> years disambiguate in the disposition cell; most do not, so the determination
> document is the authority, not the disposition string.

So for certification dispositions the collector reads the determination PDF
(`pdftotext -l 3 -layout`, whitespace-collapsed to survive line wraps) and
parses the closing sentence. The wording is stable across two decades:

| Determination | Sentence as printed |
|---|---|
| R-6952, 31 NMB No. 15 (2003) | "NOW, THEREFORE, in accordance with Section 2, Ninth, of the RLA, as amended, and based upon its investigation pursuant thereto, **the Board certifies that the Transport Workers Union of America has been duly designated and authorized to represent** for the purposes of the RLA, as amended, the craft or class of Flight Dispatchers, employees of American Airlines, Inc., its successors and assigns." |
| R-7634, 52 NMB No. 1 (2024) | "…**the Board certifies that the Brotherhood of Locomotive and Engineers and Trainmen has been duly designated and authorized to represent** for the purposes of the RLA, as amended, the craft of class of Train and Engine Service Employees, employees of TGS Cedar Port Railroad, LLC, its successors and assigns." (`craft of class` is the agency's typo) |
| R-7340, 40 NMB No. 22 (2013) | "…**the Board certifies that SMART has been duly designated and authorized to represent** for the purposes of the RLA…" |

New columns (in `WIDE_FIELDNAMES` immediately after `union_name`):

| Column | Meaning |
|---|---|
| `applicant_union` | explicit duplicate of `union_name` — the applicant, unambiguously |
| `certified_representative` | organisation named in the certification sentence, as printed, trimmed, < 200 chars |
| `certification_text_snippet` | the matched sentence, < 300 chars |
| `representation_asserted` | `true` only for a certification disposition |

`union_name` keeps its old meaning and is not renamed; downstream should prefer
`certified_representative` when it is present. When the PDF is missing,
WordPerfect-only, image-only, or the sentence does not match, both certified
columns stay **empty** and the collector logs a warning — the applicant is
never copied in.

`scrape_determinations(..., read_documents=True, fetch_pdf=None,
pdf_to_text=None, delay_seconds=...)` takes injectable doubles (tests use them;
no test touches the network), retries a failed document read once, and logs a
summary: rows, certification rows, documents read, representatives parsed, and
how many differ from the applicant.

---

## Caveats

1. **No employer address, anywhere in the listing.** Carrier name only. Same posture as `nyc-ocb-bargaining-units`: ship the wide rows, defer ACE, match to D&B DMI by name downstream. Do not invent an address to satisfy the ACE template.
2. **No `jurisdiction_state`.** Carriers are multi-state by nature — a railroad certification covers a system, not a site. Leaving it null is correct; do not guess from the carrier's HQ.
3. **One case → many rows.** Carrollton Railroad above is three rows under three case numbers for three crafts; other years reuse one case number across crafts. `row_key` must include the craft/class.
4. **`Union` is an acronym**, not a full name (`BLET`, `BMWED`, `AFA`, `IAM`, `TWU`). Occasionally it is an individual (`Robert J. Wilson (Individual)`) — RLA allows individuals as representatives. Keep verbatim; resolve acronyms downstream against the AFL affiliate registry.
5. **FY vs CY.** Pages from FY2024 on are fiscal years (Oct–Sep); earlier pages are labelled by calendar year but the first row is typically an October date, so they were already fiscal. Record `fiscal_year` from the page, not from the date.
6. **Document link moves between columns.** Through 2023 the PDF/WPD link hangs off the `Page Cite` cell; from FY2024 it hangs off the `{vol} NMB Number` cell. `_document_href` tries Page Cite, then the volume cell, then the first linked cell in the row.
7. **1990s determinations are WordPerfect** (`…/25n01.wpd`), not PDF. The document reader skips anything that is not `.pdf` and logs it; those rows keep empty certified columns.
8. **A transfer of certification is not a new certification.** `Transfer of Certification` / `Certification transferred` is 23-27 rows in some years — enough to swamp the real certifications if the classifier keyed on the word "certification" alone. It is classified `false`; if downstream wants successor-union evidence it needs its own treatment.
9. **Python `urllib` fails TLS on `nmb.gov` from macOS** (`CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical`). `curl` and `requests`/`httpx` with certifi are fine. Verify on the worker before scheduling.

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
