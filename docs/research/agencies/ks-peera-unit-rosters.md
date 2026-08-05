# Kansas PEERA unit rosters

**Status:** `collector_shipped`  
**Collector:** `ks-peera-unit-rosters`
**Source:** https://labordecisions.dol.ks.gov/PEERADocumentSearch (primary)  
**Grain:** One row per covered employer / unit roster entry.

## Collector

```bash
perb-collect ks-peera-unit-rosters --out ./out
```

Prefer the labordecisions host. `www.dol.ks.gov` is often Akamai-blocked; optional Playwright fallback needs `pip install '.[browser]'`.

