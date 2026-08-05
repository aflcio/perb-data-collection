# Washington PERC pending representation

**Status:** `collector_shipped`  
**Collector:** `wa-perc-certifications`
**Source:** https://perc.wa.gov (pending representation listing)  
**Grain:** One row per pending representation case.

## Collector

```bash
perb-collect wa-perc-certifications --out ./out
```

## Notes

Decisia / Lexum historical certification search (`decisions.perc.wa.gov`) remains CAPTCHA-gated for bulk automation. This collector covers the pending-representation table only.

