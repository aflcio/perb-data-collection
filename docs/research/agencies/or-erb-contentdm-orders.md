# Oregon ERB ContentDM final orders

**Status:** `collector_shipped`  
**Collector:** `or-erb-contentdm-orders`
**Source:** ContentDM Final Orders query API  
**Grain:** One row per ContentDM order record.

## Collector

```bash
perb-collect or-erb-contentdm-orders --out ./out
```


## Parties

The index gives no party roles, only the Official Case Name (`subjec`), so
`employer_name` and `union_name` come from the caption's vocabulary
(`party_roles`), never from which side of `v.` a party sits on. A column is
empty when the caption does not prove the role:

- an individual is never filed in either column (personnel appeals under the
  State Personnel Relations Law name no union at all);
- a caption naming two unions (a unit clarification or a competing
  representation petition) fills the employer and leaves the union empty,
  because which union represents the unit is the order's outcome;
- cross-petitions captioned twice (`A v. B and B v. A`) count each party once.

To see what a parser change would do before re-scraping, export the loaded
rows and replay them:

```bash
uv run python scripts/replay_or_erb_parties.py captions.csv --diff diff.csv
```

On 2026-09-29 against the 4,881 loaded rows: employer empty 602 to 431, both
columns empty 334 to 190, a union in the employer column 5 to 0, two unions
joined into one value 171 to 0, and union empty 865 to 965 (the two-union
rows).
