# California PERB Decision Bank

**Status:** `collector_shipped`  
**Collector:** `ca-perb-decisions`
**Source:** https://perb.ca.gov/wp-json/wp/v2/decision  
**Grain:** One row per WordPress `decision` post (~4k).

## Collector

```bash
perb-collect ca-perb-decisions --out ./out
```

Module: `perb_data_collection.collectors.ca_perb_decisions`

## Notes

- Paginate WP REST (`per_page=100`).
- Map jurisdiction suffixes (E/M/H/S/…) and description keywords into `canonical_case_type`.
- Early “CAPTCHA” notes were false positives (theme/CDN strings); the API is public.
- MMBA city/county local boards are out of scope.

