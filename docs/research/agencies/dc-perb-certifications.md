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

## Order date

`date_opened` is the petition date, not the date the Board issued the certification; in a check of 5 orders it ran 4 to 21 months ahead of when the certification actually took effect. The collector now opens each row's certification PDF and reads the date printed in the order body itself, which is the date the Board issued it. A real sample PDF carried both an e-filing stamp near the top, `Jul 25 2025 07:46PM EDT`, and a written-out date near the signature block, `July 17, 2025`; the stamp postdated the body date by over a week, so it marks receipt/filing, not issuance. The collector therefore prefers the spelled-out body date and falls back to the stamp only when no body date is found. Results land in `order_date` (ISO), `order_date_raw` (the matched text), and `order_date_source` (`body` or `stamp`); all three stay empty when the PDF has no text layer or no date, and the collector never substitutes `date_opened` for a missing order date.

