# New Hampshire PELRB bargaining-unit certifications

**Status:** `oneshot_only`  
**Collector:** `nh-pelrb-certifications`
**Source:** https://www.pelrb.nh.gov/bargaining-units (Documents API)  
**Grain:** One row per bargaining-unit certification from harvest TSV.

## Collector

```bash
perb-collect nh-pelrb-certifications --out ./out --harvest path/to/nh_pelrb_certifications.tsv
```

Live curl often returns Akamai 403; browser access works. Prefer Documents API harvest → local TSV → collector.

