# Vermont VLRB volume decisions

**Status:** `collector_shipped`  
**Collector:** `vt-vlrb-volume-decisions`
**Source:** VLRB Volumes 1–34 ZIP archives  
**Grain:** One row per PDF filename inside volume zips.

## Collector

```bash
perb-collect vt-vlrb-volume-decisions --out ./out
```

Parses ZIP membership / filenames only (no PDF text extraction).

