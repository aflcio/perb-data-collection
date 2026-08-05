# The 43 PERBs: agency profiles and collector guidance

Reference for U.S. state and territorial public-sector labor boards: what each
publishes, how searchable it is, and which connector archetype fits. Pair with
[registry.md](registry.md) for collector status and [playbook.md](playbook.md)
for research method. *Profiles last reviewed July 2026.*

---

## 1\. The ALRA Directory

**alra.org/alra-agencies/**, maintained by the agencies' own trade association (Association of Labor Relations Agencies), is the canonical seed list — current names, addresses, phone, email, and website for every U.S. state/local public-sector labor board, and an explicit list of the **19 states with "No agency exists."**

Build the agency table from this page and re-check it periodically for membership changes.

---

## 2\. Full Agency Profiles

Profiles are grouped by ETL Priority tier. Agencies not yet reached in any research pass are listed in §3 with their ALRA-sourced link only.

### TIER 1 — Build First

*(real structured search, certification-level data, or both)*

#### Ohio — State Employment Relations Board (SERB)

**Site:** serb.ohio.gov (live home `/home`; root paths 404 from some datacenter curls)

- **Searchability:** Public **Collective Bargaining Agreements** DataTable archive (**29,403** rows verified in-browser 2026-07-19) with Case Number, Employer, County, bargaining-unit code, unit size, union, start/end, Current/Previous — plus Fact-Finding / Board Opinions archives. Separate Clearinghouse DB still serves custom wage reports via research-request form (~3,584 active / 44k historical per Jan 2026 guidebook).  
- **Structured Metadata:** Yes — standardized bargaining-unit codes, employer/jurisdiction-type codes, 350+ benchmark job titles; CBA table already exposes codes + sizes without PDF NLP.  
- **Stable Identifiers:** Yes, agency-assigned bargaining-unit and case codes (e.g. `24-MED-03-0308`).  
- **Historical Depth:** Public table = filed contracts with effective date after 2000 (Current + Previous); pre-2000 via Clearinghouse request.  
- **Anti-bot Protection:** Soft — collector host curl returns **404** on home/archive; Cursor browser OK (same class as FL/NH oneshot).  
- **Recommended Connector Type:** Structured search portal (archetype 1) against the public CBA DataTable (browser/Playwright oneshot until egress clears) \+ optional Clearinghouse request for wage/pre-2000 extracts.  
- **Last Verified:** July 2026 (retest 2026-07-19 — CBA table primary)

#### Washington — Public Employment Relations Commission (PERC)

**Site:** perc.wa.gov / decisions.perc.wa.gov

- **Searchability:** Faceted full-text search (Lexum "Norma"/Decisia), 8,500+ decisions since 1976, filterable by decision number, date, parties, decision-maker, case type ("Certification"), appeal status, cited legislation, collection.  
- **Structured Metadata:** Yes, rich — the best-faceted metadata schema found in this research.  
- **Stable Identifiers:** Yes.  
- **Historical Depth:** Back to 1976\.  
- **Anti-bot Protection:** None observed; vendor platform is built for public search.  
- **Recommended Connector Type:** Modern vendor-hosted platform (archetype 2). Filter directly on case type \= Certification to get current unit descriptions without manual classification.  
- **Last Verified:** July 2026

#### Massachusetts — Department of Labor Relations (DLR) / CERB

**Site:** mass.gov/dlr, pubinfo.dlr.state.ma.us

- **Searchability:** Dedicated "Public Information Search" tool (Union Certifications, Contracts, Union reports, Case Documents with REP/WMA/ULP/…). Cert path is **employer-autocomplete gated** — `Search_Employer.ashx` returns \~**1,096** employer names (letter walk, 2026-07-19); no statewide bulk cert table. Mass.gov decisions hub **403** from engineering host.  
- **Structured Metadata:** Case-number prefixes (MUP/CAS/ARB/REP/…) pre-classify case type cheaply once a case is retrieved.  
- **Stable Identifiers:** Yes.  
- **Historical Depth:** Pubinfo corpus not fully dated this pass; older material via records request.  
- **Anti-bot Protection:** Pubinfo curl OK; Mass.gov soft-blocked from this IP.  
- **Recommended Connector Type:** Legacy government keyword search (archetype 3) via employer enumeration — high friction until a REP bulk path is proven.  
- **Last Verified:** July 2026 (retest 2026-07-19)

#### Michigan — Employment Relations Commission (MERC)

**Site:** michigan.gov/leo

- **Searchability:** Dedicated **MERC Elections Certifications Issued** year-PDF index (1996–2026, ~31 files) curl-reachable; plus decisions archives (Library of Michigan ContentDM 1965–2015 + LEO year accordion).  
- **Structured Metadata:** Year cert PDFs are **image scans** — `pdftotext` POC 2026-07-19 failed (2025: **3/82** pages with text; 2024/2022/2020/2018/1996: **0**). ContentDM decisions have party/docket but are not an elections-cert registry.  
- **Stable Identifiers:** Yes, MERC case numbers (post-OCR on sparse text pages).  
- **Historical Depth:** Cert PDFs from 1996; decisions further back.  
- **Anti-bot Protection:** None observed on LEO media URLs.  
- **Recommended Connector Type:** **Don’t build** without OCR (archetype 4 year PDFs alone are not parseable).  
- **Last Verified:** July 2026 (retest 2026-07-19 — simple parser give-up)

#### Florida — Public Employees Relations Commission (PERC)

**Site:** perc.myflorida.com

- **Searchability:** Purpose-built "Search for PERC Certifications" tool \+ separate impasse-decision search.  
- **Structured Metadata:** Certification numbers assigned; 2023 statutory changes tie recertification to a dues-paying-percentage threshold, generating longitudinal membership/density data per unit, not just a one-time certification event.  
- **Stable Identifiers:** Yes, PERC certification numbers.  
- **Historical Depth:** Not fully characterized; certification search appears current-focused.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Structured search portal (archetype 1); certification results link to PDF orders requiring a parse step.  
- **Last Verified:** July 2026

#### Iowa — Public Employment Relations Board (PERB)

**Site:** iowaperb.iowa.gov, iowa-superb.iowa.gov

- **Searchability:** A genuine "Research and Retrieval Database System" (iowa-superb.iowa.gov) — cataloged on data.gov (still listed as an active dataset as of the May 2026 data.gov metadata check) — providing full-text search across four distinct collections: Contracts (current), Contracts Archive (expired CBAs back to 2008), PERB and Court Decisions, and Neutral Decisions (fact-finding/interest arbitration). One of only a small number of states where actual CBA full text, not just case decisions, is bulk-searchable.  
- **Structured Metadata:** Search fields include number, type, affiliation, name, start/end date — a real faceted interface, though the live query tool threw an application error during an earlier research pass. The catalog listing remains current, but the live tool's stability was not directly re-tested — **retest before build.**  
- **Stable Identifiers:** Yes — PERB case numbers (e.g., "17 PERB 100825" format).  
- **Historical Depth:** Contracts Archive back to 2008; decisions further back.  
- **Anti-bot Protection:** None observed, though the live app errored once during earlier testing — treat as fragile until confirmed stable.  
- **Recommended Connector Type:** Structured search portal (archetype 1\) — likely the single best CBA full-text source of any state checked, on top of its case-decision function.  
- **Notable structural feature:** Iowa's 2017 law (HF 291\) requires recertification elections tied to CBA expiration dates for most units — a recurring, dateable representation-status signal similar to Wisconsin's, but tied to contract cycles rather than a fixed annual calendar.  
- **Last Verified:** July 2026

#### Rhode Island — State Labor Relations Board (RISLRB)

**Site:** rislrb.ri.gov

- **Searchability:** A genuine certification registry, confirmed directly this pass. The landing page (rislrb.ri.gov/Certifications.htm) links to six category pages — Firefighters, Police Officers, Certified Teachers, Municipal and Quasi-Municipal Employees, State and Quasi-State Employees, and Miscellaneous — with the Municipal category splitting further into three sub-pages (City and Town Employees, Non-Professional School Department Employees, Authorities). A parallel "Disposition of Positions" set of pages tracks unit clarifications/accretions/exclusions against each original certification. There's also a fully separate searchable decisions/orders tool at rislrb.ri.gov/lrbdec/.  
- **Structured Metadata:** Confirmed — each leaf-level category page (e.g., CityTownMuniCert.htm) is a clean HTML table: City/Town | Case Number | Representative | Date Certified | Disposition, with each cell linking to a per-case PDF (original certification order and, where applicable, a disposition order). This is a static, directly scrapable table structure, not a search form.  
- **Stable Identifiers:** Yes — RISLRB case numbers in "EE-\#\#\#\#" format (e.g., "EE-3419"), including amendment suffixes (e.g., "EE-1777A") tracked inline in the table (name changes, mergers, accretions, jurisdiction transfers all annotated in-cell with dates).  
- **Historical Depth:** Certifications on the sampled table run from the 1960s (e.g., EE-1676, 1966\) through 2023–2024 entries — a long, continuously-maintained registry.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Structured search portal (archetype 1\) — a straightforward table scrape across the 6 category pages (9 counting the Municipal sub-splits) plus the disposition-PDF links.  
- **Additional context:** Rhode Island layers five separate occupation-specific arbitration acts (firefighters, municipal police, teachers, municipal employees, state police/911/corrections) on top of the general RISLRB process, mirrored in the category-page split above.  
- **Last Verified:** July 2026

#### Wisconsin — Employment Relations Commission (WERC)

**Site:** werc.wi.gov

- **Searchability:** Full-text searchable archives spanning labor relations decisions, grievance arbitration awards, municipal interest arbitration awards, and personnel appeal decisions — confirmed directly by the agency rather than inferred. Recent decision updates surface directly on the homepage.  
- **Structured Metadata:** WERC states it runs an internal case-management system that also powers the annual certification election process electronically — i.e., the representation-election workflow itself is digitized on the back end, not just published after the fact.  
- **Stable Identifiers:** Standardized case numbers across all decision types (per agency's own description); administers 3 distinct statutes, each presumably reflected in case identifiers.  
- **Historical Depth:** Not fully re-characterized, but continuous given the "decision updates published continuously" description.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Structured search portal (archetype 1\) for the decision archive; a dedicated Annual Election Results Connector for the recurring certification data, since Spring and Fall cycles are published on separate pages.  
- **Notable structural feature:** Under 2011 Act 10, most non-public-safety municipal and state bargaining units must hold annual recertification elections — a recurring, longitudinal representation-status signal (employer, unit, union, eligible voters, votes cast, outcome) unlike almost anything else in this project except Iowa's contract-cycle-tied recertifications and Florida's dues-threshold recertification. Linking successive annual results per unit would produce a genuine longitudinal bargaining-unit-status history rather than a single certification snapshot.  
- **Last Verified:** July 2026

---

### TIER 2 — Decisions Are Public and Well-Organized

*(but no certification registry — decision-text parsing required)*

#### California — Public Employment Relations Board (PERB)

**Site:** perb.ca.gov

- **Searchability:** A Decision Bank with keyword, decision-number, and topic search, plus a "recent decisions" feed. Case numbering encodes structured information (case type, year) usable for parsing.  
- **Structured Metadata:** PERB's own case-numbering scheme is fully self-documented and encodes both case type and governing statute directly in the case number, with no NLP required for a large fraction of petitions — case-type prefixes (PC, DP, UM, AC, RR, among others) plus jurisdiction suffixes (Dills Act, EERA, HEERA, MMBA, Transit, Trial Courts, Child Care, etc.). Maps cleanly onto the canonical case\_type taxonomy in §1.  
- **Stable Identifiers:** Yes, PERB decision numbers.  
- **Historical Depth:** Not fully characterized; appears to cover recent decades well.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Government keyword search (archetype 3), decision-text parsing for unit descriptions.  
- **Caveat:** MMBA (city/county) units are governed by local rules, not PERB — scattered across city/county sites, and LA City/LA County each run their own local mini-PERB (erb.lacity.org, ercom.lacounty.gov) requiring separate connectors.  
- **Last Verified:** July 2026

#### Illinois — Illinois Labor Relations Board (ILRB) \+ Illinois Educational Labor Relations Board (IELRB)

**Site:** ilrb.illinois.gov, elrb.illinois.gov

- **Searchability:** Decisions browsable by case number; annual reports summarize case-type counts.  
- **Structured Metadata:** Minimal beyond case number and party names in the decision text itself.  
- **Stable Identifiers:** Yes, case numbers, but no certification registry.  
- **Historical Depth:** Not fully characterized.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** PDF-only/decisions-only (archetype 5), decision-text parsing.  
- **Jurisdictional note:** ILRB splits into State Panel (state govt \+ most local govt/special districts \+ RTA) and Local Panel (local govt \>2M population — effectively Chicago/Cook County) — track which panel issued a given decision.  
- **Last Verified:** July 2026 (original pass)

#### New Jersey — Public Employment Relations Commission (PERC)

**Site:** nj.gov/perc

- **Searchability:** Decisions and synopses published; index appears to run on a Lotus Notes-style document database (percdecisions.nsf URL pattern) — PDF decisions, no bulk export.  
- **Structured Metadata:** Minimal; a paid Westlaw/NJSBA-indexed alternative exists (PERC Index, 1969–present) if licensing is preferable to scraping.  
- **Stable Identifiers:** Yes, P.E.R.C. No. XXXX-XX format.  
- **Historical Depth:** Decisions referenced back to 1969 via the paid index; free site depth unconfirmed.  
- **Anti-bot Protection:** Unconfirmed.  
- **Recommended Connector Type:** PDF-only (archetype 5), decision-text parsing.  
- **Jurisdictional note (confirmed this pass):** NJ PERC's own "who is covered" guidance explicitly excludes several bi-state/independent authorities from its jurisdiction — NJ Transit Rail, the Port Authority of NY/NJ, the Waterfront Commission of NY Harbor, the Delaware River Port Authority, the Delaware River and Bay Authority, and the Delaware River Joint Toll Bridge Commission — each of which either runs (or historically ran) its own separate labor-relations mechanism outside PERC. Worth a follow-up pass to confirm which of these still maintain any kind of representation-case record at all beyond the Port Authority panel already tracked in §2/Tier 4 below.  
- **Last Verified:** July 2026

#### New York — Public Employment Relations Board (PERB) \+ NYC Office of Collective Bargaining (OCB) \+ Port Authority Employment Relations Panel

**Site:** perb.ny.gov, ocb-nyc.org

- **Searchability:** State PERB — case files by petition, no bulk export found on the state site itself.  
- **Structured Metadata:** Minimal at state level; NYC OCB and the bi-state Port Authority panel are fully separate systems requiring independent connectors, not sub-components of NYS PERB.  
- **Stable Identifiers:** Case/petition numbers exist but format not fully characterized.  
- **Historical Depth:** Historical case files/transcripts through the 1980s were reportedly transferred to the NY State Archives, originally compiled via Cornell ILR's Labor-Management Documentation Center — a possible historical-data lead distinct from the live website.  
- **Anti-bot Protection:** Unconfirmed.  
- **Recommended Connector Type:** PDF-only/decisions-only (archetype 5\) for the state PERB; the Port Authority panel has no independent website found — contact-only (phone/email), effectively Tier 4 for that sub-agency specifically.  
- **Last Verified:** July 2026 (original pass)

#### Pennsylvania — Labor Relations Board (PLRB)

**Site:** pa.gov (Dept. of Labor & Industry)

- **Searchability:** "PLRB Final Orders" published by year as flat lists with case names; e-filing accepted for most documents.  
- **Structured Metadata:** Minimal — year-indexed lists only, no search engine found.  
- **Stable Identifiers:** Case numbers referenced in each order (e.g., PLRA-C-25-16-E format), but no index searchable by number.  
- **Historical Depth:** Multiple years of "Final Orders" pages found (e.g., 2026 page); older years likely exist as separate year pages.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Year-indexed static archive (archetype 4).  
- **Last Verified:** July 2026 (original pass)

#### Minnesota — Bureau of Mediation Services (BMS)

**Site:** mn.gov/bms, **preferred ETL:** mn.gov/bms/search/ (Search All Documents)

- **Searchability:** Faceted document search (`v:sources=mn-bms-database3`) with a first-class Document Class filter — e.g. `Order-Certification of Excl Rep` returns **300** hits (verified in-browser 2026-07-19). Separate representation-decisions listing + short RSS exist but are thinner than the search corpus. Legacy `mn.gov/bms-stat` is obsolete for ETL.  
- **Structured Metadata:** Yes on search hits — Case Number, Employer Name, Union Name, Date, Doc Class, plus PDF link. Certification PDFs (“Certification of Exclusive Representative,” cases like `25PCE1106` / `14PCE0284`).  
- **Stable Identifiers:** Yes — BMS case numbers (`##PCE####`, `##PRE####`, etc.) and numeric document IDs on `documents2`.  
- **Historical Depth:** Search sample spans at least 1958–2020s for the cert class; full depth not exhaustively dated.  
- **Anti-bot Protection:** Radware on HTML search/listing paths from datacenter curl; **known `mn.gov/bms/documents2/*.pdf` URLs download without captcha** from the same host. Browser/Playwright clears search.  
- **Recommended Connector Type:** Government keyword/faceted search (archetype 3) with a bot-gated listing step (archetype 6 only for search pagination) — scrape metadata via Playwright, pull PDFs over plain HTTP.  
- **Last Verified:** July 2026 (retest 2026-07-19 — search primary confirmed)

#### Nebraska — Commission of Industrial Relations (CIR)

**Site:** ncir.nebraska.gov

- **Searchability:** A "CIR Reporter" search function plus a "Reporter and Appeals Search" providing full-text decisions in a volume-indexed static-file structure — URL pattern observed as `nebraska.gov/ncir/reporter_and_appeals_search/data/reporter/{volume}CIR_xx/{volume}CIR{page}({year}).html`, going back to the agency's first case in 1947 (published from 1974 forward as "CIR Reporter").  
- **Structured Metadata:** The volume/page/year-based URL scheme is itself a usable structured index — you can plausibly enumerate volumes and crawl systematically rather than needing a search form.  
- **Stable Identifiers:** Yes — "N CIR NNN (YEAR)" citation format used consistently.  
- **Historical Depth:** Back to 1947 (agency founding, then called Court of Industrial Relations), with CIR Reporter volumes 1–19 searchable online and volume 20+ under "Filings and Opinions."  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Year/volume-indexed static archive (archetype 4\) — a good candidate for a simple systematic crawl given the predictable URL structure.  
- **Last Verified:** July 2026

#### Oregon — Employment Relations Board (ERB)

**Site:** oregon.gov/ERB, cdm17027.contentdm.oclc.org

- **Searchability:** ERB's "Advanced Search for Board Orders" runs on OCLC's ContentDM digital-library platform (order type, year, subject facets, plus full-text search) — a genuinely structured, if library-oriented, search tool.  
- **Structured Metadata:** ContentDM exposes facet-browsable metadata; OCLC's ContentDM also has a documented API/OAI-PMH harvesting capability in many deployments, worth checking specifically for this collection.  
- **Stable Identifiers:** Yes — PECBR ("Public Employer Collective Bargaining Reporter") citation format, e.g., "21 PECBR 673."  
- **Historical Depth:** Orders before 2004 are explicitly not online — pre-2004 material exists only in print PECBR volumes at the ERB's physical library in Salem or select law libraries. A real, hard historical-depth ceiling, not a scraping limitation.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Modern vendor-hosted platform (archetype 2\) for 2004–present; pre-2004 requires manual archive digitization or a records request and should be treated as out of scope for automated ETL.  
- **Last Verified:** July 2026

#### Kansas — Public Employee Relations Board (PERB)

*(housed in the Dept. of Labor's Labor Relations Division)* **Site:** dol.ks.gov/labor-relations

- **Searchability:** Directly confirmed this pass — the "Public Employer Employee Relations Act (PEERA) Decisions" page states decisions are searchable by date, subject, or keyword, and (more valuably) the page itself already lists per-employer bargaining-unit rosters with inline status flags — e.g. a sampled entry for USD 500 (Kansas City, KS) lists Clerical, Paraprofessional, Shop & Maintenance, Security Officers, and Bus Drivers units, with an asterisk convention marking units where the "bargaining representative decertified or withdrew representation." That's meaningfully closer to a lightweight, page-embedded certification/decertification registry than a plain decision archive.  
- **Structured Metadata:** Moderate — the per-employer unit listing with decertification flags is structured in spirit even if delivered as flat HTML/PDF rather than a queryable database; the separate keyword/date/subject search covers PNA (education) and PEERA (general public-sector) decisions on two related but distinct statutory tracks.  
- **Stable Identifiers:** Not fully characterized at the case-number level; petitions require notarized paper/mailed filing (5 copies) per the agency's own instructions, suggesting the underlying case-management system is not petitioner-facing/digital, whatever the public decisions page shows.  
- **Historical Depth:** Not fully characterized.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Government keyword search (archetype 3), with the per-employer unit-roster HTML as a secondary structured-scrape target distinct from the decision-text search.  
- **Jurisdictional note:** Kansas coverage is opt-in — PEERA only applies where a city, county, or district's governing body has voted to be covered — so Kansas will always have a smaller population of covered employers than a state where coverage is automatic; this is a real scope limit on the data, not a scraping gap.  
- **Last Verified:** July 2026

---

### TIER 2B — Newly Characterized, Moderate Confidence

#### Alaska — Labor Relations Agency (ALRA-AK)

**Site:** labor.alaska.gov/laborr

- **Searchability:** Long historical decisions archive; subject-indexed digests covering representation, unit clarification, elections, contract bar, and related topics.  
- **Structured Metadata:** The subject index is a better crawl spine than crawling by year.  
- **Stable Identifiers:** Yes.  
- **Historical Depth:** Long-running; annual reports (case counts by type) available back multiple years.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Government keyword search (archetype 3), subject-index-driven crawl.  
- **Note:** State executive-branch CBA/bargaining-unit profile data now sits with the Dept. of Law (law.alaska.gov) following a 2019 reorg — a second, separate source for state-employee-specific data.  
- **Last Verified:** July 2026

#### Connecticut — State Board of Labor Relations (SBLR)

**Site:** portal.ct.gov/dol/divisions/state-board-of-labor-relations (legacy `ctdol.state.ct.us/csblr` is dead — DNS fail / portal 404 as of 2026-07-15)

- **Searchability:** Full-text board decisions (1945–today) and procedural orders still *point to* the CT DOL Document Library (`dolpublicdocumentlibrary.ct.gov/CsblrCategory?prefix=%2FCSBLR%2Fdecisions`). Live Document Library returns F5/BITS **“Request Rejected”** from curl **and** Cursor browser (2026-07-19); Wayback captures of the same URL archived the reject page, not folder listings. Legacy year HTML indexes (`laborboarddecisionsYYYY.htm`) remain usable **only via Wayback** (2023–2025 confirmed). Portal litigation list is four PDFs only.  
- **Structured Metadata:** No SBLR certification registry. Best live CT unit roster found is **OPM Office of Labor Relations** contracts ([portal.ct.gov/opm/olr-publications/contracts/office-of-labor-relations-contracts](https://portal.ct.gov/opm/olr-publications/contracts/office-of-labor-relations-contracts)) — 17 executive-branch SERA bargaining units with CBA PDFs; does not cover municipal MERA or teacher TNA units.  
- **Anti-bot Protection:** Document Library hard-blocked (BITS), not a browser-solvable CAPTCHA. OPM OLR portal has none observed.  
- **Recommended Connector Type:** **Do not build** a scheduler flow for SBLR yet. Manual/adjacent: OPM OLR contracts snapshot; optional later Wayback year-index scrape for decisions. See [ct-sblr-decisions.md](ct-sblr-decisions.md).  
- **Last Verified:** July 2026 (retest 2026-07-19)

#### Delaware — Public Employment Relations Board

**Site:** perb.delaware.gov

- **Searchability/Structured Metadata:** Decision formatting appears highly standardized; employer, union, bargaining unit, and disposition generally recoverable through deterministic parsing.  
- **Recommended Connector Type:** PDF-only with deterministic-template parsing (a standardized-template variant of archetype 5, easier to parse reliably than an arbitrary template).  
- **Last Verified:** July 2026

#### District of Columbia — Public Employee Relations Board

**Site:** perb.dc.gov

- **Searchability/Structured Metadata:** Consistent identifiers including PERB number and case number; a strong candidate for deterministic metadata extraction similar to Delaware.  
- **Recommended Connector Type:** PDF-only with deterministic-template parsing.  
- **Last Verified:** July 2026

#### Maine — Labor Relations Board (MLRB)

**Site:** maine.gov/mlrb

- **Searchability:** A Google-powered search across MLRB Hearing Examiner decisions, Board decisions, and Superior/Law Court appeals — split into two browsable sub-directories (Prohibited Practice Complaints and Unit Representation matters) each with its own index page listing every case file name, a usable enumeration mechanism independent of the search box.  
- **Structured Metadata:** Decisions are color-coded by source on the rendered page. More importantly, Maine maintains a page specifically for "Notices of Unit Agreements, Voluntary Recognition, Disclaimers and Revocation of Certification" — meaning Maine is one of the few states in this research that appears to track voluntary recognitions, not just contested certifications, directly addressing the "voluntary recognition is invisible" gap flagged in earlier versions.  
- **Stable Identifiers:** Yes — case file names double as citations (e.g., "83-06").  
- **Historical Depth:** PPC decisions complete from 1977 to date; older representation-case digitization described as ongoing.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Government keyword search (archetype 3), with the static index pages as a supplementary/backup enumeration method. Also has a dedicated (separately-requested) CBA database in development — status not re-checked this pass; worth a follow-up ping to the agency before the next research cycle.  
- **Last Verified:** July 2026 — upgraded from unverified to Tier 2 given the voluntary-recognition tracking and dual index pages.

#### Hawaii — Labor Relations Board (HLRB)

**Site:** labor.hawaii.gov/hlrb

- **Searchability:** Representation information primarily embedded inside decisions.  
- **Recommended Connector Type:** PDF-only/decisions-only (archetype 5); expect to rely on text extraction rather than structured downloads.  
- **Last Verified:** July 2026

---

### TIER 2C — Moderate-to-Good Confidence

#### Montana — Board of Personnel Appeals (BOPA)

**Site:** erd.dli.mt.gov, ebizws.mt.gov; **adjacent ETL:** doa.mt.gov (state CBAs), dli.mt.gov/hearings/decisions/ (CB filter)

- **Searchability:** Official BOPA Decision Search at ebizws.mt.gov/ERD\_PUBLICPORTAL/searchform?mylist=bopa is a real form, but returns **Request Rejected** from curl **and** Cursor browser (2026-07-19) — same hard block class as CT Document Library. No certification registry HTML found. Better live sources: (1) DOA OLR bargaining-agreements accordion (state executive units + CBA PDFs); (2) DLI Hearings decisions page with a Collective Bargaining filter (**109** PDF cards, mostly 2001–2018). Older “Fact Finder Decisions” leaf URLs under erd.dli.mt.gov are **404**.  
- **Structured Metadata:** None on the blocked portal. DOA page embeds unit codes (e.g. MFPE `(011)`) and primary CBA links. Hearings cards expose case number, date, caption, PDF URL.  
- **Stable Identifiers:** Hearings case numbers (e.g. `661-2018`); DOA unit codes on state CBAs. BOPA board citation format not confirmed live (portal blocked).  
- **Historical Depth:** Hearings CB filter spans ~2001–2018 with one 2025 unit-determination; post-2018 publication looks thin. DOA CBAs are current-contract focused (2025–2027 cycle on sampled links).  
- **Anti-bot Protection:** **Hard block** on `ebizws.mt.gov` BOPA portal (browser-unsolvable). DOA and DLI Hearings HTML/PDFs reachable with no captcha from this host.  
- **Recommended Connector Type:** **Do not build** a scheduler flow for BOPA yet. Manual/adjacent: DOA OLR units snapshot + optional DLI CB decision index. See [mt-bopa-decisions.md](mt-bopa-decisions.md).  
- **Note:** Statute still charges BOPA with unit determination and certification (MCA 39-31); the earlier “appellate-only” framing understated original representation work. Public ETL still depends on decision PDFs / adjacent state CBA lists, not a cert registry.  
- **Last Verified:** July 2026 (retest 2026-07-19 — portal still rejected; adjacent snapshots taken)

#### Nevada — Government Employee-Management Relations Board (EMRB)

**Site:** emrb.nv.gov

- **Searchability:** No full-text search engine found, but decisions are flat PDFs at a predictable path, and a separate "Log of Open Cases" page tracks pending matters by stage (motion queue, hearing queue — split geographically into Las Vegas and Northern Nevada dockets).  
- **Structured Metadata:** Minimal beyond item number/case number embedded in filenames and decision text.  
- **Stable Identifiers:** Yes — sequential item numbers plus an internal case number (e.g., "045825") appear in every filename.  
- **Historical Depth:** Decisions found from the 2010s forward; full depth unconfirmed.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** PDF-only/decisions-only (archetype 5); the sequential item-number filenames make systematic enumeration plausible even without a search form, similar to Nebraska's scheme.  
- **Note:** EMRB's jurisdiction covers local government employers specifically (formally the "Local Government Employee-Management Relations Board" in most decision captions) — worth confirming whether state-government employees are covered by a separate mechanism.  
- **Last Verified:** July 2026

#### Vermont — Labor Relations Board (VLRB)

**Site:** vlrb.vermont.gov

- **Searchability:** Genuinely strong for an agency this size: decisions since 1977 are packaged by volume as downloadable zip files (37+ volumes), each unpacking to one file per decision. A separate cumulative A–Z subject index maps subject terms directly to volume/page citations.  
- **Structured Metadata:** The subject index is a ready-made crawl spine, similar in spirit to Alaska's subject-indexed digests.  
- **Stable Identifiers:** Yes — Volume-Page citation format, with a "\#" flag in the subject index marking decisions appealed to and decided by the Vermont Supreme Court.  
- **Historical Depth:** Complete back to 1977\.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Year/volume-indexed static archive (archetype 4\) — download each volume zip, parse the subject index separately as a metadata layer, join on volume-page citation.  
- **Note:** A single board administers seven separate acts; notably does not handle unit-determination or representation elections under the Teachers Act specifically (only ULP charges involving teachers), so that act needs special-cased handling.  
- **Last Verified:** July 2026

#### New Hampshire — Public Employee Labor Relations Board (PELRB)

**Site:** www.pelrb.nh.gov (preferred), nh.gov/pelrb (legacy)

- **Searchability:** Modern **Bargaining Units** registry at `/bargaining-units` backed by Documents API (`field_document_subcategory=706`) — **653** certification PDFs with title, date, union taxonomy (verified 2026-07-19). Legacy year-indexed board-decision PDFs still exist under `nh.gov/pelrb/decisions/board/`.  
- **Structured Metadata:** Yes on the cert registry (Drupal id, posted date, union category, PDF URL). Decision archive remains thin beyond year-sequence IDs.  
- **Stable Identifiers:** Certification document ids; legacy decisions use "PELRB Decision No. {year}-{number}".  
- **Historical Depth:** Cert dates in the live registry span at least 1976–2026.  
- **Anti-bot Protection:** **Akamai 403** from the engineering host (and PDF CDN `mm.nh.gov`); browser / residential egress works.  
- **Recommended Connector Type:** Structured search portal (archetype 1) via Documents API when egress clears; until then oneshot TSV harvest + CLI (same class as FL PERC).  
- **Last Verified:** July 2026 (retest 2026-07-19 — Bargaining Units API primary)

#### Puerto Rico — Junta de Relaciones del Trabajo (JRT)

**Site:** jrt.pr.gov

- **Searchability:** Decisions and orders live under a year/month-indexed path on the territorial document host — systematically enumerable, similar in spirit to Nebraska's or Vermont's volume schemes. The JRT site also publishes "Órdenes de Elección" (election orders) and "Censos de los Trabajadores Sindicados" (unionized-worker census documents).  
- **Structured Metadata:** Minimal on the decisions themselves (PDF only), but Puerto Rico's central statistics agency, estadisticas.pr.gov, separately publishes a periodically-updated "Directorio de Uniones ante la Junta de Relaciones del Trabajo" — a structured directory of union names, employers, presidents, and contact information.  
- **Stable Identifiers:** Case numbers appear in decision filenames/text (e.g., "PC-2009-43" paired with a decision number like "D-2010-1443").  
- **Historical Depth:** Decisions found back to at least 2010; full depth unconfirmed.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Year/month-indexed static archive (archetype 4\) for decisions; a separate lightweight periodic-fetch connector for the estadisticas.pr.gov union directory.  
- **Important jurisdictional caveat:** JRT's founding statute, the Puerto Rico Labor Relations Act (Law No. 130), is modeled on the NLRA and is historically a private-sector labor relations law. Puerto Rico's public-sector employees are governed by separate legislation, so JRT case data may skew private-sector and should not be assumed to be a public-sector PERB equivalent without confirming case-type breakdowns first — a risk that the corpus itself is the wrong population, not merely that decisions are hard to parse. Recommend an explicit scoping check (sampling case captions for government-employer parties) before building.  
- **Last Verified:** July 2026

#### Maryland — Public Employee Relations Board (PERB) / Public School Labor Relations Board (PSLRB) / State Higher Education Labor Relations Board (SHELRB)

**Site:** laborboards.maryland.gov

- **Searchability:** All three legally distinct boards are unified behind one search interface, with separately searchable collections for Unfair Labor Practice Decisions, Unit Clarification, Negotiability, Election Certifications, and Impasse Decisions — filterable by employer type (State Agencies / Higher Education / Public Schools) rather than by board.  
- **Structured Metadata:** The Election Certification database is first-class, not embedded-in-decisions: it stores Certification of Representative records with employer type, case number, date, and a linked PDF, covering historical certifications from all three legacy boards alongside current PERB records. case\_type maps directly onto the canonical taxonomy in §1 without needing decision-text inference.  
- **Stable Identifiers:** Yes — standardized docket numbering confirmed across all three boards' historical and current records.  
- **Historical Depth:** Spans current PERB records plus legacy SLRB/PSLRB/SHELRB certifications; exact earliest date unconfirmed.  
- **Anti-bot Protection:** None observed.  
- **Recommended Connector Type:** Structured search portal (archetype 1\) — one connector, parameterized by board/employer-type; the Election Certification collection specifically should be prioritized as a near-Tier-1 certification registry.  
- **Last Verified:** July 2026

#### New Mexico — Public Employee Labor Relations Board (PELRB)

**Site:** pelrb.nm.gov

- **Searchability:** Dedicated sections for Court Decisions, Hearing Examiner Decisions, Arbitration Awards, Bargaining Units, Bargaining Representatives, and Collective Bargaining Agreements.  
- **Structured Metadata:** The dedicated Bargaining Units/Representatives/CBA sections imply structured underlying records, not just decision prose — worth a full engineering pass to confirm field-level detail and export options.  
- **Stable Identifiers:** Not yet confirmed at the field level.  
- **Historical Depth:** Not yet confirmed.  
- **Anti-bot Protection:** Not yet confirmed.  
- **Recommended Connector Type:** Likely archetype 1 (structured search portal) pending direct verification; also retains its existing value as host of the cross-state "129 Public Sector Collective Bargaining by State" reference document (§4).  
- **Last Verified:** July 2026 — still needs the same detailed pass given to other Tier 2C agencies before committing scraper time.

#### Indiana — Education Employment Relations Board (IEERB)

**Site:** in.gov/ieerb

- **Searchability:** A genuine searchable database (registration required to search, but the function itself is public) covering CBAs, unit determinations, ULP decisions, fact-finding cases, compliance reports, and Attorney General opinions relevant to IEERB matters.  
- **Structured Metadata:** Multiple distinct case/document categories suggest structured underlying records, though exact field-level detail wasn't captured.  
- **Stable Identifiers:** Not yet confirmed at the field level.  
- **Historical Depth:** Not yet confirmed.  
- **Anti-bot Protection:** A free account is required to use the search engine — not a bot-block, but an access-friction step (may need a persistent authenticated session).  
- **Recommended Connector Type:** Structured search portal (archetype 1), gated by account registration.  
- **Note:** Still an education-only jurisdiction — Indiana has no general public-sector PERB — but this upgrades Indiana from "PDF archive, education-only" to "structured multi-category database, education-only." Model as a specialized education-only connector.  
- **Last Verified:** July 2026

---

### TIER 3 — Confirmed to Exist

*(characterized only at a high level; still needs a dedicated verification pass before scraping)*

| Jurisdiction | Agency | URL | What's Known |
| :---- | :---- | :---- | :---- |
| **Missouri** | State Board of Mediation | labor.mo.gov/SBM | Structurally, Missouri is better than previously assumed: SBM has broad statutory jurisdiction over "most public employees" (state, counties, cities, school districts), publishes a documented representation-petition process, and now accepts petitions online. But its 2024 department annual report discloses that the Board "has not had a quorum since July 2024" following the departure of its sole labor-side member — meaning new certifications/elections may be stalled or backlogged regardless of the source's data quality. Note also the carve-outs: police, deputy sheriffs, highway patrolmen, Missouri National Guard, and teachers are excluded from SBM's secret-ballot-election jurisdiction (per Chapter 105 RSMo and *Eastern Missouri Coalition of Police v. City of Chesterfield* / *City of Grandview* case law), and in practice many police/teacher units nationwide organize via card-check or municipal ordinance instead — meaning SBM's own registry, even once unblocked, will still undercount public-safety and education bargaining units specifically. No searchable case/certification database was found on labor.mo.gov/SBM itself; still recommend a records-request approach, but the population question is now better scoped than "likely never existed." |
| **Arizona** | Phoenix Employment Relations Board (local only) | phoenix.gov/perb | Arizona has no state PERB; Phoenix's is the only ALRA-member body in the state — a live example of the "home-rule labor board" pattern discussed in §3. A spot-check of Austin, San Antonio, Nashville, and Louisville found no evidence that any of them run a dedicated municipal labor-relations board comparable to Phoenix's — Austin and San Antonio's public-sector labor relations appear to run through Texas's local-option Ch. 174 police/fire framework (tracked municipally, not via a standing board) and general HR/civil-service channels rather than a PERB-style body; Nashville's public-sector bargaining is limited to the teacher-only "collaborative conferencing" mechanism already noted in §3; no Louisville-specific board was found either. Treat "is Phoenix unique among the four next-most-likely home-rule candidates" as answered (yes) rather than open, while leaving the door open for other home-rule cities not yet checked. |
| **New York/New Jersey** | Port Authority Employment Relations Panel | *(no website found)* | Confirmed again: no independent website. However, Panel decisions are cited in a consistent reporter format visible in state-court opinions — e.g. "97 PAERP 28" (*In re an Alleged Improper Practice under Section XI(A)(d) of the Port Auth. Labor Relations Instruction*) — implying an internal "PAERP" citation series exists even without a public index. Worth a targeted records request or a search of NJ/NY state-court case law (which does cite PAERP decisions directly) as a secondary route to reconstructing a partial decision list, rather than treating this purely as contact-only. Still effectively Tier 4 for direct ETL purposes. |

---

## 3\. What to Do About the 19 "No Agency" States

Texas Local Government Code Ch. 174 (police/fire opt-in bargaining by referendum, tracked municipally not statewide); Kentucky's urban-county and police-specific statutes; Tennessee's teacher-only "collaborative conferencing" board; home-rule cities creating their own local boards even absent a state one (Phoenix is the existence proof, and the Austin/San Antonio/Nashville/Louisville check found no comparable peer); Colorado as a genuinely moving target given its recent extensions of bargaining rights. For the remainder: city council/county commission minutes, union self-reported affiliate lists, and news coverage are the only realistic (manual, Tier 4\) leads.

### Colorado Detail

Colorado doesn't fit cleanly into "no agency" anymore and is worth its own line rather than a footnote. Two separate, real mechanisms now exist:

- **COBCA (Collective Bargaining by County Employees Act, C.R.S. Title 8, Art. 3.3):** Covers county employees in counties with population over 7,500 (per the most recent decennial census); it explicitly does *not* apply to a City and County (i.e., not Denver or Broomfield), municipalities, schools, or special districts. The state's Division of Labor Standards and Statistics (part of CDLE, cdle.colorado.gov) determines the appropriate bargaining unit absent party agreement and conducts representation elections — this is a genuine, if narrow, state-administered representation-election function that belongs in the connector inventory even though it isn't a freestanding "PERB."  
- **Denver:** A separate case entirely: voters approved Referred Question 2U in November 2024 granting most non-supervisory City and County of Denver employees (career service, City Council, Library Commission, Civil Service Commission, Board of Adjustment, Denver Water — but not Denver Health & Hospital Authority career-service staff, and not police/fire/sheriff, who already bargain) the right to collectively bargain, effective January 1, 2026\. Critically, the implementing ordinance (24-716, finalized in the council's Oct. 2025 committee vote) does **not** create a new Denver labor board — disputes are routed mostly to a city-appointed arbitrator, and the existing Career Service Board's role is explicitly preserved rather than replaced. This means Denver will generate real bargaining-unit and election data starting in 2026 with no ALRA-style board to scrape it from; the City Clerk / Office of Human Resources labor-relations pages are the most likely eventual home for any published unit/election data and should be watched going forward rather than assumed absent.

---

## 4\. Cross-State and Historical Sources

- NCSL's two bargaining-law databases  
- NCTQ's collective bargaining law database  
- The New Mexico PELRB-hosted "129 Public Sector Collective Bargaining by State"  
- The NBER Public Sector Collective Bargaining Law Data Set  
- Cornell ILR/Catherwood's CBA archive  
- Kate Bronfenbrenner's offered 1999–2003 dataset  
- BLS's 1985 *Monthly Labor Review* survey

---

## Connector Archetypes

| \# | Archetype | Example Agencies |
| :---- | :---- | :---- |
| 1 | **Structured search portal with certification/case-type filtering** | Ohio, Florida, Washington, Maryland, Rhode Island (RISLRB certification tables). Build one faceted-search scraper, configure per agency. |
| 2 | **Modern vendor-hosted decision platforms** (Lexum/Decisia "Norma," OCLC ContentDM, etc.) | Washington, Oregon. Worth recognizing as a platform, not a one-off: the same scraping logic works across every agency that licenses the same vendor product. |
| 3 | **Government-hosted keyword/case-number search** (legacy or modern) | Massachusetts, Michigan, California, Maine, Iowa, Alaska, Kansas. (Montana BOPA portal listed historically but **blocked** — see MT notes.) |
| 4 | **Year- or volume-indexed static archives** | Connecticut, Nebraska (CIR Reporter by volume), Vermont (volume zips), New Hampshire, Puerto Rico (year/month), older Oregon PECBR pre-2004 (offline entirely). |
| 5 | **PDF-only annual reports/orders with no search** | Pennsylvania (by-year lists), New Jersey, Nevada (sequential filenames), many of the agencies once verified only at a high level. |
| 6 | **Bot-protected or fragile legacy portals** | Minnesota's bms-stat subdomain; expect more of these on \*.state.xx.us domains. |
| 7 | **No online agency presence at all / manual enrichment only** | The 19 "no agency" states (with the Colorado caveats above), plus Virgin Islands PERB, the Port Authority panel, Missouri (pending its quorum situation), and any narrow occupation-specific statutes within "no agency" states. |

---

## TIER 4 — Confirmed to Exist, No Searchable Online Archive Found

*(contact/records-request only)*

#### Virgin Islands — Public Employees Relations Board (VI-PERB)

**Site:** viperb.org

- **Status:** Confirmed to be an active, currently-staffed board (FY2026 territorial budget testimony names a sitting chair, executive director, and legal staff), operating under Title 3 of the Virgin Islands Code and the Public Employees Labor Relations Act. No searchable decisions database, case index, or bulk document archive found on viperb.org or elsewhere.  
- **Recommended Connector Type:** None — Tier 4, manual/records-request enrichment only, alongside the Port Authority panel and the 19 "no agency" states.  
- **Last Verified:** July 2026

---

## Canonical Case-Type Taxonomy

Several agencies with strong structured metadata (Maryland, California, and — by extension — Ohio/Florida/Washington's certification/decision splits) turn out to be independently converging on the same handful of case categories, just under different names and prefixes. Rather than storing each agency's native vocabulary as-is, the `case_event` table should normalize into one shared `case_type` enum, with a per-agency mapping table translating native codes into it:

| Canonical `case_type` | Example Native Codes/Labels |
| :---- | :---- |
| **CERTIFICATION** | CA "PC" (Petition for Certification), MD "Election Certifications," FL/WA certification search hits, RI "Certifications of Representatives" |
| **DECERTIFICATION** | CA "DP" (Decertification Petition), KS's decertification/withdrawal flags embedded in its per-employer unit rosters |
| **UNIT\_CLARIFICATION / UNIT\_MODIFICATION** | CA "UM," MD "Unit Clarification," RI "Disposition of Positions" |
| **AMENDMENT\_OF\_CERTIFICATION** | CA "AC" |
| **RECOGNITION** | CA "RR" (Request for Recognition), MD implicitly via certification records for voluntarily recognized units |
| **ULP** (unfair labor practice) | MD "Unfair Labor Practice Decisions," MA "MUP" prefix, most Tier 2 decision archives |
| **NEGOTIABILITY** | MD "Negotiability" |
| **IMPASSE** | MD "Impasse Decisions," MA "CAS"/arb-adjacent categories |
| **ARBITRATION** | MA "ARB" prefix, Vermont/VLRB grievance decisions |
| **FACT\_FINDING** | Ohio Fact-Finding Reports, Indiana IEERB fact-finding cases |
| **SEVERANCE** | Occurs in some unit-modification contexts; kept distinct since it's a narrower action than a full unit clarification |

California's own case-numbering scheme is a useful worked example: CA case numbers combine a case-type prefix (PC/DP/UM/AC/RR/etc.) with a jurisdiction suffix identifying the governing statute (Dills Act, EERA, HEERA, MMBA, Transit, Trial Courts, Child Care, etc.) — meaning a large fraction of CA petitions can be classified by regex against the case number alone, with no NLP or decision-text parsing required.

Maryland's Election Certification database (spanning current PERB and legacy SLRB/PSLRB/SHELRB certifications under one interface) is the other strong example: it already stores `case_type` as a first-class filterable field rather than something to infer from text.

Rhode Island's certification tables are a third worked example, confirmed directly this pass: each row is already keyed by case number, representative, and certification date, with a separate linked "Disposition" record — so CERTIFICATION and UNIT\_CLARIFICATION events map onto RISLRB's table structure with no NLP required either.

Kansas's per-employer unit rosters are a fourth, lighter-weight example — decertification is a first-class inline flag on an otherwise plain HTML page, so DECERTIFICATION events can be extracted there without decision-text parsing, even though the source isn't a database in the RISLRB/Maryland sense.

Where an agency's own metadata already carries this information, map it directly; where it doesn't (most Tier 2/3 decision archives), decision-text classification remains necessary, but the target schema they're being classified into should be this shared enum.

---

## Revised Remaining Research Priorities

The highest-value remaining research targets are:

1. **Field-level verification passes on New Mexico PELRB and Indiana IEERB** — both confirmed structurally rich, neither has had the detailed field-by-field engineering pass given to Maryland or Rhode Island, and neither was reached again this pass.  
2. **Missouri's quorum status** — worth a direct follow-up before investing any scraping effort: confirm whether SBM has regained a quorum since the July 2024 gap disclosed in its FY2024 annual report, since that determines whether new representation data is even being generated right now, independent of whatever's discoverable online.  
3. **Hidden statewide CBA repositories in "no agency" states** — departments of labor/administration may collect contracts without administering representation as such. Colorado's COBCA (state-administered, county-only representation elections) is a concrete example surfaced this pass of exactly this pattern — worth checking whether other "no agency" states have a similarly narrow, easy-to-miss statutory carve-out administered outside a named PERB.  
4. **Denver's post-2U data source** — no board was created, so there's no obvious ALRA-style scrape target yet; the City Clerk / Office of Human Resources Labor Relations pages should be monitored starting in 2026 as the city's first bargaining units and elections are processed.  
5. **Municipal labor boards outside ALRA membership, remaining candidates** — ruled out Austin, San Antonio, Nashville, and Louisville as Phoenix-style peers; the broader question of whether other home-rule cities run their own boards remains open beyond those four.  
6. **New Jersey's excluded bi-state/independent authorities** (NJ Transit Rail, Waterfront Commission of NY Harbor, Delaware River Port Authority, Delaware River and Bay Authority, Delaware River Joint Toll Bridge Commission) — confirmed this pass to sit outside NJ PERC's jurisdiction; unconfirmed whether any of them maintain a representation-case record of their own beyond the already-tracked Port Authority panel.  
7. **Port Authority panel reconstruction via case law** — rather than treating it as contact-only, a search of NJ/NY state-court opinions citing the "PAERP" reporter format (e.g., "97 PAERP 28") could reconstruct a partial decision index as a secondary source.  
8. **Kansas case-number/identifier scheme** — Kansas was upgraded structurally this pass, but its stable-identifier format at the individual-case level (as opposed to the per-employer unit roster) still needs direct confirmation before a connector is built.

**Next step recommendation:** Reply to Bronfenbrenner to accept the 1999–2003 database now, ask about the recoverability of the early-90s all-states data, and ask whether her data captures independent (non-national-affiliate) unions — the population that "no agency" states and voluntary-recognition gaps will otherwise always miss. Maine's voluntary-recognition tracking is the one partial exception found so far.
