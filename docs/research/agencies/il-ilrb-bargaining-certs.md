# Illinois ILRB bargaining-unit certifications

**Status:** `collector_shipped`  
**Collector:** `il-ilrb-bargaining-certs`
**Source:** ILRB fiscal-year certification PDF index  
**Grain:** One row per FY certification line item.

## Collector

```bash
perb-collect il-ilrb-bargaining-certs --out ./out
```

Requires `pdftotext -layout`. IELRB is out of scope.


## Five tables per volume, and header-driven mapping

A fiscal-year PDF is not one table. Each volume holds up to five, each with its
own banner, its own header row and its own set of columns:

| Banner | Columns |
| --- | --- |
| Certifications of representative | Case Number, Employer, Labor Organization, Date Certified, Prevailing Party, No. of Employees, Unit Certified |
| Certification of voluntarily recognized representative | Case Number, Employer, Labor Organization, Date Certified, Unit Certified |
| Amendment to certifications | Case Number, Employer, Labor Organization, Date Certified, Amendment |
| Certifications of gubernatorial designation of position excluded from collective bargaining (the S-DE table) | Case Number, Employer, Date Certified, State Agency, No. of Positions, Unit Positions |
| Revocation of prior certification | Case Number, Employer, Labor Organization, Date Certified, Unit Type |

Older volumes use slightly different wording for the same column, such as
Certification Date, Date Revocation, Unit Description or Unit Type, and some
later tables print only a banner and reuse the previous table's layout.

The S-DE table is the one that matters most, because it has no Labor
Organization column at all. Reading every table with one column map, detected
from the first header row, sliced the Date Certified value into the union name
on those rows, so a designation such as S-DE-14-054 arrived with a union of
19/2013 and a state agency thrown away.

The collector now splits the text into sections at every header row, and also
at an inner banner where a later table reuses the layout above it. Each section
computes its own column bounds from its own header, reading the wrapped second
header line above it so that No. of Positions and Unit Positions are told
apart. Cells are then mapped by header label rather than by position:

- Employer to `employer_name`
- Labor Organization to `union_name`, absent in the S-DE table, so those rows
  carry an empty union by construction rather than by cleanup
- Certified, Certification Date and Date Revocation to `certified_date`
- Prevailing Party to `prevailing_party`
- No. of Employees and No. of Positions to `employees`
- Unit Certified, Unit Description, Unit Type, Amendment and Unit Positions to
  `bargaining_unit_name`, joined with a semicolon when a table has more than
  one descriptive column
- State Agency to `agency`, a column of its own rather than being folded into
  the employer name

Two more columns appear in the wide CSV: `agency` after `employer_name`, and
`table_heading` after `fiscal_year`, which records the banner the row was
printed under.

A table's header prints once but the table runs over many pages, and later
pages drift a few glyphs. So the header positions are only a hint. Each row is
re-anchored on the line that carries its date, which is the one line with every
column filled, and each line then snaps its boundaries onto its own runs of two
or more spaces. Companion case numbers are still merged, either when they are
stacked with a literal "and" between them or when a bare case number with no
employer and no date sits under an earlier designation. A blank line alone no
longer merges two rows, which it used to do throughout the S-DE table.

Known remaining gaps, both in the vertically centred volumes from FY25 onward,
where a wrapped cell is printed above its case number rather than below it:

- A handful of rows still take a neighbour's employer or union text when two
  rows are printed with no blank line between them.
- A row whose only wrapped fragment is a bare number, such as a local number
  split off from its union name, can attach that number to the employer.
