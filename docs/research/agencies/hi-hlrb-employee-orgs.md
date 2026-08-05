# Hawaii HLRB employee organizations

**Status:** `collector_shipped`  
**Collector:** `hi-hlrb-employee-orgs`
**Source:** HLRB List of Employee Organizations PDF (HRS Ch. 89)  
**Grain:** One row per exclusive-rep × bargaining unit.

## Collector

```bash
perb-collect hi-hlrb-employee-orgs --out ./out
```

Requires `pdftotext`.

