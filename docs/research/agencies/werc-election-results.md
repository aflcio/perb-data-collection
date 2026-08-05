# Wisconsin WERC election results

**Status:** `collector_shipped`  
**Collector:** `werc-election-results`
**Source:** WERC annual election-result PDF index  
**Grain:** One row per election unit parsed from result PDFs.

## Collector

```bash
perb-collect werc-election-results --out ./out
```

Requires poppler `pdftotext` on `PATH`.

