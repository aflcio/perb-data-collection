# New Jersey PERC issued decisions

**Status:** `collector_shipped`  
**Collector:** `nj-perc-issued-decisions`
**Source:** HCL Domino IssuedDecisions ExpandView XML  
**Grain:** One row per issued decision PDF entry.

## Collector

```bash
perb-collect nj-perc-issued-decisions --out ./out
```

## Representation note (2026-08-26)

IssuedDecisions is a **case / ULP archive**, not a certification registry. In CLRR staging,
`union_name` is empty on all ~5.2k rows; parties (if any) live only in linked PDFs. Do **not**
chase bulk PDF NLP of this feed for exclusive-rep evidence.

**Better primary for representation:** Public Sector Contracts (Domino) search by employer /
organization / unit description:

https://perc.state.nj.us/publicsectorcontracts.nsf/Contracts%20By%20Employer%20Search/$searchForm?SearchView

Fields of interest: Employer Name, Organization Name (union), Contract Term, Unit Description.
Filing is incomplete (OSC ~2024: roughly one-third of entities with a current contract), but the
row shape matches CBA/unit representation. Next step: harvest/ExpandView research POC, not
IssuedDecisions enrichment.

See [representation-gaps-2026-08-26.md](../representation-gaps-2026-08-26.md).
