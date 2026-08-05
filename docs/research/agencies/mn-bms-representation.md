# Minnesota BMS exclusive-rep certifications

**Status:** `oneshot_only`  
**Collector:** `mn-bms-certifications`
**Source:** https://mn.gov/bms/search/ (Order-Certification of Excl Rep)  
**Grain:** One row per certification document from harvest JSONL.

## Collector

```bash
perb-collect mn-bms-certifications --out ./out --harvest path/to/mn_bms_certifications.jsonl
```

Live search is often WAF/CAPTCHA gated. Harvest listing metadata separately (browser/WebFetch), then ingest with the collector. PDF CDN URLs are often curl-reachable even when search is not.

