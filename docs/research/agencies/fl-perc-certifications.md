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


## Dossier pass

Each grid row links a certification dossier PDF at `certification_pdf_url`. The
collector fetches that file for every row (`read_documents=True`, one retry on a
transient failure) and lands seven extra columns from it.

### Readability is measured on the bytes

An earlier flag guessed readability from the file name and was wrong in both
directions on roughly a third of the 2,186 rows. `pdf_probe.probe_pdf_bytes`
reads the file instead. It asks three questions: does the PDF declare a font
resource (`/Font`), does it contain an image XObject (`/Subtype /Image`), and do
its content streams contain text-showing operators (`Tj`, `TJ`, `'`, `"`)?
Content streams are inflated with zlib first, because most are `FlateDecode`
compressed. A file counts as image-only when it carries an image, declares no
font, and shows either no text operators or fewer than 40 extractable
characters. Malformed bytes return a probe with an error and no verdict, and the
row keeps empty columns rather than a guess.

Text is then extracted with poppler `pdftotext -layout`, which returns an empty
string on any failure, so "no text" and "could not read" behave the same way.

### The last order decides the status

A dossier is not one order. It is the stack of orders filed against one
certification number over the years, oldest first, so the last order in the file
is the one that governs. The collector splits the text at ALL CAPS heading lines
naming an order or a certification, takes the closing section, and looks there
for a revoking signal: `REVOKING CERTIFICATION`, `is hereby REVOKED`, a
certification that is revoked, a petition to disclaim interest that is GRANTED,
a disclaimer of interest, or any form of decertification. All matching is
case-insensitive. A match makes the row `revoked` and records the matched phrase
in `revocation_signal`. A readable dossier with no such signal is `in_effect`.
An image-only or unreadable dossier is `unknown`, because nothing was read.

The date printed nearest each heading is parsed in both `Month D, YYYY` and
`MM/DD/YYYY` form. The date on the closing order becomes `latest_order_date`,
and the earliest date on a certification-type order becomes
`certification_order_date`, which is the issue date the warehouse otherwise
lacks.

### Columns landed

`is_image_only` (`true`, `false`, or empty when unknown), `text_chars`,
`certification_status` (`in_effect`, `revoked`, `unknown`), `latest_order_title`,
`latest_order_date` (ISO), `revocation_signal`, `certification_order_date`
(ISO). They sit in `WIDE_FIELDNAMES` immediately after `pdf_file_name`.

The run logs progress every 200 rows and closes with a summary of rows, PDFs
fetched, image-only files, revoked, in effect, unknown, and failures.
