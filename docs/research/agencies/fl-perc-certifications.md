# Florida PERC certifications

**Status:** `oneshot_only`  
**Collector:** `fl-perc-certifications`
**Source:** https://perc.myflorida.com (cert search + CertNo gap fill)  
**Grain:** One row per PERC certification number.

## Collector

```bash
perb-collect fl-perc-certifications --out ./out
```

## Notes

- Structured certification search works when reachable (~2,185 certs).
- Many datacenter/egress paths time out on curl. Prefer browser or an IP that can reach the host.
- Do not assume a reliable cron from every network.

