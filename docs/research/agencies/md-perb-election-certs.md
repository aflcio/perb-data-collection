# Maryland PERB election certifications

**Status:** `collector_shipped`  
**Collector:** `md-perb-election-certs`
**Source:** https://laborboard.maryland.gov/ (election certifications listing)  
**Grain:** One row per published election certification (complete set, ~36).

## Collector

```bash
perb-collect md-perb-election-certs --out ./out
```

The collector asserts the page’s displayed total matches the parsed row count.

