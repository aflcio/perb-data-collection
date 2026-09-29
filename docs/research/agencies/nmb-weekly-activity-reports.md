# National Mediation Board — weekly activity reports

**Status:** `collector_shipped`
**Agency:** National Mediation Board (NMB), federal, Railway Labor Act.
**Collector slug:** `nmb-weekly-activity-reports`
**Last researched:** 2026-09-29

---

## Why this agency is in scope

[`nmb-representation-determinations`](nmb-representation-determinations.md) lands the Board's
certifications. A certification exists only where a craft or class was organised, or re-run,
since the listing began in 1998. Units that have held a craft without a new election since then
never appear there. Measured against CLRR's determinations mart on 2026-09-29: APA at American and
SWAPA at Southwest have no certification, and of the Class I railroads only one CSX coal-loading
unit does, so BLET, SMART-TD and BMWED at Union Pacific, BNSF and CSX are absent. Airline mergers
forced new elections, so Delta/ALPA (2009) and United/AFA and ALPA (2011) *are* in the listing;
an earlier draft of this doc named them as missing, which was wrong.

The weekly activity reports close that gap. Every week the Board lists the mediation cases it
docketed, assigned, settled and released, as well as the representation cases it opened, balloted
and closed. Each row names a carrier, an organisation and usually a craft or class. The NMB
mediates a Section 6 dispute only between a carrier and its employees' representative. So a
mediation docket is the Board's own record that an organisation is bargaining for that craft at
that carrier.

---

## Primary source

| Item | Value |
|------|-------|
| **Archive index** | `https://nmb.gov/NMB_Application/index.php/archived-weekly-activity-reports/` |
| **Current-year index** | `https://nmb.gov/NMB_Application/index.php/weekly-activity-report-2/` (December 2025 on) |
| **Year pages** | 28, 1998–2025. Paths drift: `1998-weekly-activity-reports/` … `2022-…`, then `2023-weekly-activity-report/` (singular) and `archived-weekly-activity-reports/2024-weekly-activity-reports/` (nested) |
| **Report pages** | ~50 a year, 1,439 in total. Slugs usually name the week (`weekly-activity-report-july-5-9-2004/`), but some are bare post ids (`19048-2/`), a few are misspelled (`janurary`), and some sit under `weekly-activity-report-2/` |
| **Format** | WordPress posts. Plain HTML `<table>` per section in every year, 1998–2026. No PDF |
| **Grain** | one row per report week × section × table row × case number |
| **Reachability** | curl OK. WP REST gated (see the determinations doc) |

### Measured (full crawl, 2026-09-29)

| Measure | Value |
|---|---|
| Reports discovered | 1,439 (1 dead link, 1 report posted twice, 49 weeks with no table because the week had nothing, "No report this week", or "None" in every section) |
| Rows | 11,858 |
| Distinct case numbers | 3,314 |
| Report weeks | 1998-02-20 to 2026-09-25 |
| `A-` Section 6 mediation cases | 1,255 distinct (4,748 rows) |
| `GM-` grievance mediation cases | 125 distinct (310 rows) |
| `R-` representation cases | 1,048 distinct (5,205 rows) |
| `CR-` representation applications | 418 distinct (738 rows) |

New `A-` dockets per year run from 116 (1998) to the teens (2016, 2020, 2021), with 26 by September 2026.

Rows by section: elections underway 2,995; meetings, training and facilitation 1,950; new dockets
1,464; cases closed 1,366; settlements 1,343; new applications 1,136; ballots mailed 745; cooling-off
and strike activity 585; cases assigned 237; interference 32; elections authorized 5.

### Sample rows (verbatim)

```
Week ending 1999-07-09 | Settlements        | A-12961 | Duluth, Missabe & Iron Range | BLE  | Tentative Agreement
Week ending 2010-11-19 | New Dockets        | A-13586 | Continental Airlines         | IAM  | Flight Attendants | Sims
Week ending 2010-11-19 | New Dockets        | GM-0104 | Miami Air International      | AFA  | Flight Attendants
Week ending 2010-11-19 | New Applications   | CR-6999 | Delta Air Lines              | IAM  | 2200-Office and Clerical Employees
Week ending 2010-11-19 | Elections Underway | R-7257  | Delta Air Lines              | IAM  | 16,500- Passenger Service | 12/07/2010
Week ending 2024-02-16 | Meetings, Training, and Facilitation | T-515 | Norse Atlantic Airways | AFA | TBD
Week ending 2024-02-16 | New Applications   | R-7626  | Louisville & Indiana Railroad | SMART | 17 – Train and Engine Service
```

---

## Case-number prefixes

The prefix is the Board's case type. The collector keeps every prefix and records it in
`case_prefix`; deciding what each one means as evidence is a downstream call.

| Prefix | Distinct cases | Where it appears | Meaning |
|---|---|---|---|
| `A-` | 1,255 | new dockets, settlements, meetings, cooling-off | Section 6 mediation between a carrier and a representative |
| `GM-` | 125 | new dockets, meetings, assigned | Grievance mediation |
| `T-` | 201 | "Meetings, Training, and Facilitation" | Training and facilitation work, not a dispute |
| `F-` | 70 | meetings, dockets, settlements (1998–2003) | Facilitation |
| `OP-` | 24 | new dockets (2006–2007) | Outreach programmes; the carrier cell can be an event ("APFA BOD Forum") |
| `R-` | 1,048 | applications, ballots, elections, closed | Representation case |
| `CR-` | 418 | applications, closed | Representation application file number |
| `RD-` | 25 | elections, closed | Representation case (decertification-style run-off) |
| `CJ-`, `C-`, `CA-` | 90, 37, 15 | applications, closed, new dockets (1998) | Older case series |

---

## Connector shape

1. **Discovery.** Read the archive index and keep every link whose path ends in
   `(19|20)\d\d-weekly-activity-report(s)?/`, wherever it is nested. Add the current-year index.
   Never hardcode the years. On each index page, a link counts as a report when its slug names a
   week *or* its link text reads "Weekly Activity Report" / "Week Ending": bare post-id slugs are
   only recognisable by their text.
2. **Report week** is parsed from the heading, then the `<title>`, then the slug. Handled forms:
   "November 15 — November 19, 2010", "Week Ending July 9, 1999", "September 4-8, 2006",
   "December 20 through 24, 1999", "December 29, 2025 – January 2, 2026", and `janurary`.
3. **Sections.** The report is flattened into text blocks and table rows in document order.
   Each table is filed under the nearest section label, which sits either in a paragraph above
   the table or in the table's own first row. An unrecognised heading ending in a colon
   ("Ratifications:" before the pattern knew it) starts an `unclassified` section, so its rows
   are never filed under the section above. Arbitration tables (NRAB/PLB/SBA caseload counts)
   are skipped.
4. **Columns** are mapped by name through synonym sets, never by position, except where no
   header was printed (below).
5. **Duplicates.** A report posted twice under two URLs (`march-11-15-2024` carries the March
   18–22 report) is detected by its content and dropped. Row keys are
   `NMB-WAR:{week_end}:{section}:{case}:{org}:{craft}`, with an ordinal suffix when a report prints
   the same line twice.
6. **Cadence:** monthly, with the other NMB collector. A full run is ~1,450 requests at a 0.3 s delay.

### Header and layout drift

| Variant | Years | Handling |
|---|---|---|
| `Case No.` / `Case #` / `Case Nos.` / `Case No. Docket Date` | all | case column. A docket date printed in the case cell is split out |
| `Org.` / `Union` / `Org./Craft or Class` | all / 2024+ | org column. The combined column is split on `/` |
| `Class/Craft` / `Craft or Class` / `Craft/Class` / `Proposed Craft or Class` | all | craft column |
| `Approx. No. of Emp.-Craft or Class` (`335-Mechanics and Related Employees`, `16,500- Passenger Service`) | all | split into `approx_employees` and `craft_class` |
| `Carrier (Craft/Class)` (`Air Wisconsin (Mechanics)`) | 2001–2002 | craft taken from the parenthesis |
| `BLET/Locomotive Engineers` in the Org. cell | 2020s ratifications | split when no craft column is printed |
| `Closing` | 1998 settlements | status |
| Header row printed as its own one-row table above the data table | 1998 | header persists until the next section label |
| No header row at all | 1998 (3 tables) | positional fallback per section |
| One cell per row ("Case No.", "Carrier", … then the values) | May 1999 | regrouped by header width |
| `A12882` (no dash), `A-12798& A-12803`, `A-12897-99` (a range) | 1998 | parsed; ranges expanded up to 12 cases |
| Bare `13476` in a mediation table | 2011, 2020 | read as `A-13476` |
| `GM-83` and `GM-0083`, `T-515` and `T-0197` | 2004–2026 | `GM`, `T`, `F`, `OP`, `TF` numbers zero-padded to four digits |

---

## Caveats

1. **No employer address.** Carrier name only, as on the determinations listing. No
   `jurisdiction_state`: a craft or class is system-wide.
2. **Carrier names are free text.** 1,119 distinct raw spellings on the `A-`/`GM-` rows ("United",
   "United Airlines", "UAL"). Resolve downstream.
3. **Org is an acronym**, sometimes two (`SMART & TOPS`, `IAM-AMFA`), sometimes a coalition
   ("Coalition", "Multiple"). Keep verbatim.
4. **A case number can be printed against the wrong carrier.** Week ending 2011-07-29 lists
   "A-13584 A-13586 A-13587 | American Airlines | TWU" in the meetings table, while A-13586 is
   docketed and settled as Continental Airlines / IAM. Downstream should key on the new-docket row
   and treat meeting rows as secondary.
5. **National rail bargaining** appears under the carriers' conference (`NCCC`, "Several",
   "Multiple"), not under each Class I railroad.
6. **Known losses.** Two May 1999 reports print misaligned one-cell-per-row tables in their
   representation sections; 14 rows across the corpus have no parseable case number.
7. **TLS from an inspected network.** On a host behind Zscaler TLS inspection (this research
   host), Python `urllib` fails with `CERTIFICATE_VERIFY_FAILED` because the proxy re-signs nmb.gov
   with a root that only the macOS keychain trusts; curl works. This is the same failure the
   determinations doc records as caveat 9, and it is the host, not nmb.gov. The FirstLogic worker
   already runs the determinations collector with the same client.

---

## Link research

| URL | Role | Result from this host | Notes |
|-----|------|----------------------|-------|
| `…/archived-weekly-activity-reports/` | archive index | 200 | 28 year-page links |
| `…/weekly-activity-report-2/` | current-year index | 200 | 39 reports, December 2025 on |
| `…/2023-weekly-activity-report/` | year page | 200 | singular slug |
| `…/archived-weekly-activity-reports/2024-weekly-activity-reports/` | year page | 200 | nested under the archive |
| `…/19761-2/` | report | 404 page | dead link on the current-year index |
| `knowledgestore.nmb.gov` | document archive (Angular + Elastic API) | 200 | contracts, pre-1998 determinations and awards. Out of scope here |
| `nmb.my.salesforce-sites.com/caseload` | arbitrators' case report | 200 | behind a terms-of-use gate. Out of scope |

---

## Verdict

- **Better link found?** This is a second primary, not a replacement: it reaches the units the
  determinations listing cannot.
- **Build collector?** **Yes, shipped.** Plain HTTP, 28 years of stable HTML tables, drift handled
  by name mapping and a handful of layout fallbacks.
- **Scope caveats:** RLA carriers only. Carrier names without addresses.

---

## Next

- [x] Implement `perb_data_collection/collectors/nmb_weekly_activity_reports.py`
- [x] Add row to [registry.md](../registry.md)
- [ ] FirstLogic side: thin re-export shim + wide/S3/BQ load; ACE deferred (no address)
