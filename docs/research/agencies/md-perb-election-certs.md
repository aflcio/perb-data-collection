# Maryland PERB election certifications

**Status:** `collector_shipped`  
**Collector:** `md-perb-election-certs`
**Source:** https://laborboard.maryland.gov/ (election certifications listing)  
**Grain:** One row per unique published board document (34 unique PDFs from 36 listing entries).

## Collector

```bash
perb-collect md-perb-election-certs --out ./out
```

The collector asserts the page’s displayed total matches the parsed row count.

## Source quirks

- The listing titles are not structured party data. They inconsistently combine case numbers,
  unions, employers, bargaining units, and intervenors, so generic comma or dash splitting is not
  safe. Employer and union fields are normalized per document from the linked board PDFs.
- `/media/<id>` links are direct PDFs even though the URLs do not end in `.pdf`.
- Media IDs `260` and `412` are the same PDF, as are `310` and `425`. The collector retains the
  lower media ID in each pair and omits the duplicate listing entry.
- Three older documents do not publish a case number in the listing title. Those values remain
  blank instead of being inferred.
- Some PDFs are image-only. The collector does not OCR them at ingestion time; the verified party
  normalization is explicit, while PDF reading and citation remain CLRR curation concerns.
