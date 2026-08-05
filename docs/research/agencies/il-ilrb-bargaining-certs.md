# Illinois ILRB bargaining-unit certifications

**Status:** `collector_shipped`  
**Collector:** `il-ilrb-bargaining-certs`
**Source:** ILRB fiscal-year certification PDF index  
**Grain:** One row per FY certification line item.

## Collector

```bash
perb-collect il-ilrb-bargaining-certs --out ./out
```

Requires `pdftotext -layout`. IELRB is out of scope.

