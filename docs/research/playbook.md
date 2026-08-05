# PERB research playbook

Playbook for researching a U.S. state/territorial PERB (or peer board) before
writing a collector. Goal: find a **better primary** than a stale bookmark,
classify reachability, and leave written artifacts.

## Inputs

| File | Role |
|------|------|
| [43-states-perb.md](43-states-perb.md) | Agency profile, tier, archetype |
| [registry.md](registry.md) | Status, prior blocked notes |
| [agencies/](agencies/) | Per-agency plans |

Canonical seed list if the agency is missing: **alra.org/alra-agencies/**

## Checklist

1. Load prior research (registry + 43-states + plan)
2. Dual probe known URLs (CLI curl/HTTP vs browser)
3. Hunt better primary (cert registry > structured API > decisions > adjacent)
4. Sample fields / count / grain
5. Verdict + status
6. Write plan + update registry + 43-states snippet
7. Optional oneshot harvest before a collector

## Dual probe (required)

Always compare **plain HTTP** (curl / `urllib`) with a **real browser**. Do not
conclude “CAPTCHA forever” from curl alone — and do not conclude “unblocked”
from a soft 200 HTML page that is actually a reject interstitial.

| Observation | Likely class | Next move |
|-------------|--------------|-----------|
| Curl fails; browser 200 + real listing/API | Soft bot gate | Browser/Playwright harvest; try plain HTTP on known PDF URLs |
| Curl **and** browser “Request Rejected” / BITS | Hard WAF | Do **not** build; seek adjacent pages or records request |
| Curl timeout; browser works | Egress / IP limit | Oneshot / off-host harvest; **no** scheduled collector |
| Page has “captcha” strings but API/HTML works | False positive | Ship normally |
| Form/search works; no bulk list | High friction | Document; defer |

Probe the **listing/search** URL and any **PDF/document CDN** separately.

## Hunt a better primary

Search order (stop when you have a structured, countable corpus):

1. Certification / exclusive-rep / bargaining-unit registry
2. Structured API / vendor platform (WP REST, Drupal Documents API, ContentDM, Lexum)
3. Faceted search with usable metadata
4. Year/volume static indexes
5. Adjacent agencies (OLR/DOA/OPM) — label as **adjacent**, not the PERB itself
6. Wayback only as bootstrap when live is hard-blocked

## Sample fields and grain

Record:

- Hit/total count
- Grain (one row per cert / case / unit / decision)
- Stable ids
- Listing fields available **without** PDF NLP
- Employer/union presence
- PDF or permalink reachability

Map native labels toward the shared `canonical_case_type` enum in
[schema.md](../schema.md) / [43-states-perb.md](43-states-perb.md).

## Verdict matrix

| Verdict | Registry status | Collector? |
|---------|-----------------|------------|
| Reliable HTTP scrape | `collector_shipped` | Yes |
| Corpus good; host 403/timeout | `oneshot_only` | CLI from harvest file |
| Primary found; not coded yet | `collector_ready` / `planned` | Scaffold when ready |
| PERB blocked; adjacent list usable | `adjacent` / PERB `blocked` | Document snapshot only |
| Hard WAF or no registry | `blocked` | Do not scaffold |
| Sub-agency only | partial note | Wire only what’s real |

Prefer honest “don’t build yet” over a fragile scheduled scrape.

## Anti-patterns

- Trusting curl-only “blocked” without a browser check (or vice versa)
- Scheduling collectors for hosts that always 403/timeout
- Treating adjacent OLR CBA lists as the PERB certification registry
- Leading with dead legacy URLs when a cert search/API exists
- Shipping CAPTCHA-solving SaaS as a project feature
