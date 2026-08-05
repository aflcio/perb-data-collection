# DC PERB certifications

**Status:** `collector_shipped`  
**Collector:** `dc-perb-certifications`
**Source:** https://casesearch.perb.dc.gov/?docType=Certifications  
**Grain:** One row per certification / recognition listing entry (single HTML page, no pagination).

## Collector

```bash
perb-collect dc-perb-certifications --out ./out
```

Module: `perb_data_collection.collectors.dc_perb_certifications`

## Case-type mapping

| Native code | `canonical_case_type` |
|-------------|------------------------|
| RC | RECOGNITION |
| AC | AMENDMENT_OF_CERTIFICATION |
| RD | DECERTIFICATION |
| UC | UNIT_CLARIFICATION |
| UM / UCN / CU | UNIT_MODIFICATION |
| U | ULP |

Employer is the Respondent agency; complainant is typically the union. `jurisdiction_state=DC`.

