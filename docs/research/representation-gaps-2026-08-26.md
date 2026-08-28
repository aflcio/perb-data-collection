# Representation-only PERB gaps — 2026-08-26

**Scope:** What still yields **exclusive-rep / certification / unit roster / CBA-with-union-employer** evidence.  
**Out of scope here:** scrape-quality reloads on already-shipped collectors (operator-owned).  
**Related:** [registry.md](registry.md), [playbook.md](playbook.md), CLRR empty-union ticket `infra-24`.

## Network blocks (not Zscaler)

PERB scrape research does **not** name Zscaler. CLRR Zscaler notes are about BigQuery TLS, not board hosts.

| Pattern | Boards | Guidance |
|---------|--------|----------|
| Soft bot gate (curl fails, browser OK) | FL, NH, OH, often KS www | Oneshot / Playwright harvest; do not schedule from flogic |
| Hard WAF / reject | CT SBLR (BITS), MT BOPA, MN search (Radware) | Do not fight; adjacent lists or records request only |
| Akamai 403 | NH (`pelrb.nh.gov`, `mm.nh.gov`), sometimes KS www | Browser Documents API / alternate host |
| Decisia / Lexum CAPTCHA | WA historical certs, NY Lexum | No CAPTCHA SaaS; FOIA if historical WA is required |
| Egress timeout | FL `perc.myflorida.com` | Off-host / browser refresh of existing oneshot |

Laptop Zscaler changes will not make flogic curl clear Akamai or BITS.

## Highest-value remaining representation work

### 1. Ohio SERB public CBA archive (`planned`)

- **Why it counts:** Structured employer + union + unit code + size + dates + PDF. Same product role as eCommons PERB CBAs / NYC OCB (who represents which public unit), not election ballots.
- **Source:** https://serb.ohio.gov/view-document-archive/collective-bargaining-agreements (DataTable ~29,403 rows; still live as of this note).
- **Blocker:** Soft gate (browser OK; curl often 404). Jul-19 harvest stalled on local Playwright/CDP tooling, not missing data.
- **Path:** Off-host Chrome/Playwright dump → harvest file → oneshot ACE/Redshift. No Prefect cron until plain HTTP works.
- **Plan:** [agencies/oh-serb-clearinghouse.md](agencies/oh-serb-clearinghouse.md)

### 2. New Jersey: pivot off IssuedDecisions

- **Current problem:** `nj-perc-issued-decisions` ships ~5.2k rows with **no `union_name`**. Evidence kind is organizing/decision archive, not a cert registry. Bulk PDF NLP of that docket is the wrong chase for representation.
- **Better primary:** Domino Public Sector Contracts search — Employer, Organization (union), Contract Term, Unit Description:  
  https://perc.state.nj.us/publicsectorcontracts.nsf/Contracts%20By%20Employer%20Search/$searchForm?SearchView
- **Caveat:** OSC found incomplete filings (roughly one-third of entities with a current contract). Still far more useful than an empty-union decision bank.
- **Path:** Research POC (ExpandView / browser harvest). Do not invest in IssuedDecisions PDF party extraction for representation.
- **Plan:** [agencies/nj-perc-issued-decisions.md](agencies/nj-perc-issued-decisions.md)

### 3. Michigan MERC — soft re-probe only

- **Status:** Still `blocked` on image-scan year cert PDFs ([agencies/mi-merc-certifications.md](agencies/mi-merc-certifications.md)).
- **Check:** Re-run `pdftotext` on **2024–2026** year PDFs from  
  https://www.michigan.gov/leo/bureaus-agencies/ber/michigan-employment-relations-commission/merc-elections-certifications  
- **If text recovers:** small year-PDF cert collector is justified.  
- **If still image:** leave blocked; no OCR project unless tooling is explicitly wanted.

## Oneshots we already have (refresh only)

These are representation corpora already in Redshift. Network blocks affect **refresh and document curation**, not “missing state.”

| Board | Corpus | Block | Action |
|-------|--------|-------|--------|
| NH PELRB | ~653 bargaining-unit certs | Akamai 403; PDF CDN also 403 for curation | Browser Documents API → TSV when stale; no cron |
| FL PERC | ~2,185 certs | Host timeout from datacenter; sparse PDFs/dates | Browser / off-host refresh; no cron |
| MN BMS | ~338 exclusive-rep orders | Radware on search; `documents2` PDFs often plain HTTP | Browser JSONL harvest refresh |

## Explicit don’t-chase (representation filter)

| Board / path | Why skip |
|--------------|----------|
| CT SBLR Document Library | Hard BITS reject even in browser; OPM OLR is executive CBA only |
| MT BOPA portal | Portal Rejected; DOA OLR / DLI adjacent is thin |
| WA Decisia historical certs | CAPTCHA; pending-rep feed is not durable representation |
| NY statewide PERB cert index | Lexum CAPTCHA; eCommons CBA + NYC OCB already cover what we have |
| MA DLR employer-walk | No bulk cert list; high friction |
| AK ALRA decision PDF NLP | Empty union on shipped index; DoL unit profiles are state-employee only |
| KS PEERA roster | No union column (structural); small |
| VT VLRB OCR | Park image PDFs |
| CA PERB Decision Bank as cert evidence | Noisy decision NLP; not a cert registry |
| IN / PR / Phoenix / VI / PAERP | Thin, education-only, municipal, or no public index |
| IssuedDecisions / ULP party enrichment | Wrong evidence kind for “who is certified” |

## Recommended order

1. **OH SERB** oneshot harvest (largest structured employer+union gap).
2. **NJ Contracts-by-Employer** research POC (replace empty-union decisions story).
3. **MI** `pdftotext` probe on 2024–2026 year PDFs (gate any MI build).
4. **Optional:** NH / FL / MN browser refresh when those corpora go stale.

No CAPTCHA-solving SaaS. No scheduled collectors on soft/hard WAF hosts until a plain HTTP primary is proven.
