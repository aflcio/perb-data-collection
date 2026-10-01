# Maryland PERB election certifications

**Status:** `collector_shipped`  
**Collector:** `md-perb-election-certs`
**Source:** https://laborboard.maryland.gov/ (election certifications listing)  
**Grain:** One row per unique published board document (35 unique documents from 37 listing entries, 2026-09-30).

## Collector

```bash
perb-collect md-perb-election-certs --out ./out
```

The collector asserts the page’s displayed total matches the parsed row count.

## Source quirks

- The listing titles are not structured party data. They inconsistently combine case numbers,
  unions, employers, bargaining units, and intervenors, so generic comma or dash splitting is not
  safe. Employer and union fields are normalized per document from the linked board PDFs.
- `/media/<id>` links are direct PDFs even though the URLs do not end in `.pdf`. The exception is
  media `500` (PERB EL 2026-01, February 5, 2026): the board uploaded a saved Acrobat browser-viewer
  page in place of the certification, served as `application/pdf`. Its parties come from the listing
  title alone, with MPEC expanded as media `274` names it.
- Listing `<article>` elements carry an open class list. By 2026-09-30 the board had added an empty
  modifier class (`maryland-listing-item__`), which a fixed-attribute match read as zero articles.
- Media IDs `260` and `412` are the same PDF, as are `310` and `425`. The collector retains the
  lower media ID in each pair and omits the duplicate listing entry.
- Three older documents do not publish a case number in the listing title. Those values remain
  blank instead of being inferred.
- Some PDFs are image-only. The collector does not OCR them at ingestion time; the verified party
  normalization is explicit, while PDF reading and citation remain CLRR curation concerns.
