# State PERB collector registry

Current status of U.S. state and territorial public-sector labor board collectors
in this repository. Agency background: [43-states-perb.md](43-states-perb.md).
How we research boards: [playbook.md](playbook.md). Per-agency notes:
[agencies/](agencies/).

**Statuses**

| Status | Meaning |
|--------|---------|
| `collector_shipped` | Collector in package; HTTP/API path works for routine use |
| `oneshot_only` | Corpus available via harvest file or browser; live curl often blocked |
| `collector_ready` | Primary found; collector not coded yet |
| `planned` | Research points to a clear path; not coded |
| `blocked` | Hard WAF, image-only PDFs, or no usable registry |
| `adjacent` | PERB itself blocked; useful adjacent agency list documented |
| `partial` | Some feeds shipped; main board representation still missing |
| `not_started` | Named board; little or no collector work yet |
| `no_agency` | ALRA reports no freestanding board |

Run any shipped collector: `perb-collect <slug> --out ./out` (see `perb-collect --list`).

## Agencies

| Jurisdiction | Agency | Status | Collector slug | Notes | Plan |
|--------------|--------|--------|----------------|-------|------|
| Ohio | SERB | planned | — | Public CBA DataTable ~29,403 rows (browser OK; curl often 404). Top remaining candidate. | [oh-serb-clearinghouse.md](agencies/oh-serb-clearinghouse.md) |
| Washington | PERC | collector_shipped | `wa-perc-certifications` | Pending-representation listing. Decisia historical cert search still CAPTCHA. | [wa-perc-certifications.md](agencies/wa-perc-certifications.md) |
| Massachusetts | DLR/CERB | not_started | — | Employer autocomplete (~1,096 names); no bulk cert list. | [ma-dlr-certifications.md](agencies/ma-dlr-certifications.md) |
| Michigan | MERC | blocked | — | Year cert PDFs are image scans; needs OCR. | [mi-merc-certifications.md](agencies/mi-merc-certifications.md) |
| Florida | PERC | oneshot_only | `fl-perc-certifications` | ~2,185 certs. Many hosts time out on curl; use browser/off-host refresh. | [fl-perc-certifications.md](agencies/fl-perc-certifications.md) |
| Iowa | EAB (PERB) | collector_shipped | `ia-eab-unit-certifications` | ~1,005 unit-cert listing rows. SuPERB search still broken. | [ia-eab-unit-certifications.md](agencies/ia-eab-unit-certifications.md) |
| Rhode Island | RISLRB | collector_shipped | `rislrb-certifications` | Certification listing tables. | [rislrb-certifications.md](agencies/rislrb-certifications.md) |
| Wisconsin | WERC | collector_shipped | `werc-election-results` | Election-result PDFs via `pdftotext`. | [werc-election-results.md](agencies/werc-election-results.md) |
| California | PERB | collector_shipped | `ca-perb-decisions` | WP REST Decision Bank (~4k). | [ca-perb-decisions.md](agencies/ca-perb-decisions.md) |
| Illinois | ILRB | collector_shipped | `il-ilrb-bargaining-certs` | FY certification PDFs. IELRB out of scope. | [il-ilrb-bargaining-certs.md](agencies/il-ilrb-bargaining-certs.md) |
| New Jersey | PERC | collector_shipped | `nj-perc-issued-decisions` | Domino IssuedDecisions XML (~5k PDFs). | [nj-perc-issued-decisions.md](agencies/nj-perc-issued-decisions.md) |
| New York | PERB + NYC OCB | partial | `nyc-ocb-bargaining-units` | OCB 85-unit roster shipped. Live `perb.ny.gov` representation absent; Lexum CAPTCHA. | [nyc-ocb-bargaining-units.md](agencies/nyc-ocb-bargaining-units.md) |
| Pennsylvania | PLRB | collector_shipped | `pa-plrb-final-orders` | Year-indexed Final Orders PDFs. | [pa-plrb-final-orders.md](agencies/pa-plrb-final-orders.md) |
| Minnesota | BMS | oneshot_only | `mn-bms-certifications` | Harvest JSONL ingest; live search CAPTCHA/WAF. | [mn-bms-representation.md](agencies/mn-bms-representation.md) |
| Nebraska | CIR | collector_shipped | `ne-cir-reporter` | Reporter volume directories. | [ne-cir-reporter.md](agencies/ne-cir-reporter.md) |
| Oregon | ERB | collector_shipped | `or-erb-contentdm-orders` | ContentDM Final Orders API. | [or-erb-contentdm-orders.md](agencies/or-erb-contentdm-orders.md) |
| Kansas | PEERA | collector_shipped | `ks-peera-unit-rosters` | Prefer `labordecisions.dol.ks.gov`; www often Akamai (Playwright fallback). | [ks-peera-unit-rosters.md](agencies/ks-peera-unit-rosters.md) |
| Alaska | ALRA | collector_shipped | `ak-alra-board-decisions` | Decision & Order PDF index. | [ak-alra-board-decisions.md](agencies/ak-alra-board-decisions.md) |
| Connecticut | SBLR | blocked | — | Document Library BITS-blocked. Adjacent OPM OLR contracts only. | [ct-sblr-decisions.md](agencies/ct-sblr-decisions.md) |
| Delaware | PERB | collector_shipped | `de-perb-decisions` | Year-indexed decision PDFs. | [de-perb-decisions.md](agencies/de-perb-decisions.md) |
| DC | PERB | collector_shipped | `dc-perb-certifications` | Casesearch certification DataTable. | [dc-perb-certifications.md](agencies/dc-perb-certifications.md) |
| Maine | MLRB | collector_shipped | `me-mlrb-unit-rep-cases` | Unit/representation case index. | [me-mlrb-unit-rep-cases.md](agencies/me-mlrb-unit-rep-cases.md) |
| Hawaii | HLRB | collector_shipped | `hi-hlrb-employee-orgs` | HRS Ch. 89 exclusive-rep PDF (needs `pdftotext`). | [hi-hlrb-employee-orgs.md](agencies/hi-hlrb-employee-orgs.md) |
| Montana | BOPA | blocked | — | Portal rejected. Adjacent DOA OLR / DLI snapshots. | [mt-bopa-decisions.md](agencies/mt-bopa-decisions.md) |
| Nevada | EMRB | collector_shipped | `nv-emrb-employer-directory` | Local government employer directory PDF. | [nv-emrb-employer-directory.md](agencies/nv-emrb-employer-directory.md) |
| Vermont | VLRB | collector_shipped | `vt-vlrb-volume-decisions` | Volume ZIP indexes (PDF filenames). | [vt-vlrb-volume-decisions.md](agencies/vt-vlrb-volume-decisions.md) |
| New Hampshire | PELRB | oneshot_only | `nh-pelrb-certifications` | Harvest TSV from Documents API; live curl often Akamai 403. | [nh-pelrb-decisions.md](agencies/nh-pelrb-decisions.md) |
| Puerto Rico | JRT | not_started | — | Thin online election set; private-sector skew. | [pr-jrt-directory.md](agencies/pr-jrt-directory.md) |
| Maryland | PERB | collector_shipped | `md-perb-election-certs` | Complete published listing (36 rows). | [md-perb-election-certs.md](agencies/md-perb-election-certs.md) |
| New Mexico | PELRB | collector_shipped | `nm-pelrb-bargaining-units` | All-known bargaining units PDF. | [nm-pelrb-bargaining-units.md](agencies/nm-pelrb-bargaining-units.md) |
| Indiana | IEERB | not_started | — | Education-only; guest WebDocs. | [in-ieerb-bargaining-units.md](agencies/in-ieerb-bargaining-units.md) |
| Missouri | SBM | blocked | — | Quorum gap since 2024 (not a URL problem). | — |
| Arizona | Phoenix PERB | not_started | — | Municipal only (~7 MOUs). | [az-phoenix-perb.md](agencies/az-phoenix-perb.md) |
| Port Authority | PAERP | not_started | — | No public index. | — |
| Virgin Islands | VI-PERB | not_started | — | Contact / records only. | — |
| Colorado | COBCA / Denver | not_started | — | Not a freestanding statewide PERB. | — |
| 19 states | — | no_agency | — | See [43-states-perb.md](43-states-perb.md) §3. | — |

## Reachability lessons

Keep these next to the registry so new contributors do not rediscover them the hard way:

| Pattern | Boards | Guidance |
|---------|--------|----------|
| Soft bot gate (curl fails, browser OK) | FL, NH, OH, often KS www | Document oneshot / Playwright; do not pretend cron will work from every IP |
| Hard WAF / reject page | CT SBLR, MT BOPA, MN search | Do not build a scheduled collector; seek adjacent lists or records requests |
| False-positive “captcha” strings | CA PERB | Confirm real API/HTML payload before marking blocked |
| Image-only PDFs | MI MERC | Needs OCR; plain `pdftotext` is not enough |
| Better primary than the bookmark | IA EAB vs SuPERB; KS labordecisions vs www; NH Documents API | Prefer cert registries and structured APIs |

## Priorities

1. **OH SERB** CBA archive oneshot (~29k structured rows).
2. Optional: MA employer-walk cert POC; IN only if education scope is wanted.
3. Leave MI/CT/MT blocked until a real primary or OCR path exists.
