# Michigan MERC election certifications

**Status:** `blocked`  
**Collector:** none yet
**Source:** MERC Elections Certifications Issued year-PDF index  
**Grain:** Year PDFs exist but are mostly image scans.

## Notes

`pdftotext` historically does not recover usable text on most pages (e.g. 2025 POC: few
pages with text). Do not build a collector without a confirmed text path.

**2026-08-26:** Soft re-probe only. Re-run `pdftotext` on **2024–2026** year PDFs from the
index before starting any OCR project. If text recovers, a small year-PDF cert collector is
justified. If still image-only, leave `blocked`.

Index: https://www.michigan.gov/leo/bureaus-agencies/ber/michigan-employment-relations-commission/merc-elections-certifications

See [representation-gaps-2026-08-26.md](../representation-gaps-2026-08-26.md).
