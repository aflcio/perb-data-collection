# Nevada EMRB employer directory

**Status:** `collector_shipped`  
**Collector:** `nv-emrb-employer-directory`
**Source:** Local Government Employer Data PDF  
**Grain:** One row per employer × union × unit.

## Collector

```bash
perb-collect nv-emrb-employer-directory --out ./out
```

Requires `pdftotext -layout`.

