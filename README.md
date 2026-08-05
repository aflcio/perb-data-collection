# PERB Data Collection

Open-source **research** and **collectors** for U.S. state and territorial
public-sector labor boards (PERBs and peers): certifications, bargaining-unit
rosters, election results, and decision indexes.

Collectors write **local wide CSV** (shared core columns plus agency-specific
extras). This project does **not** load warehouses, geocode addresses, or publish
harvested corpora.

## Install

```bash
# From a clone
pip install -e .

# Optional Playwright (needed for some bot-gated sites, e.g. KS PEERA fallback)
pip install -e '.[browser]'
playwright install chromium

# Dev / tests
pip install -e '.[dev]'
```

Some PDF-layout collectors also need [poppler](https://poppler.freedesktop.org/)
`pdftotext` on your `PATH`.

## Collect

```bash
perb-collect --list
perb-collect dc-perb-certifications --out ./out
```

Oneshot / harvest-file collectors (e.g. MN BMS, NH PELRB):

```bash
perb-collect mn-bms-certifications --out ./out --harvest path/to/harvest.jsonl
```

## Library API

```python
from pathlib import Path
from perb_data_collection.collectors.dc_perb_certifications import scrape_to_wide_csv

n = scrape_to_wide_csv(Path("out/dc_perb_certifications.csv"))
```

## Research

Agency profiles, reachability notes, and field maps live under
[`docs/research/`](docs/research/). Start with:

- [`docs/research/43-states-perb.md`](docs/research/43-states-perb.md) — agency profiles
- [`docs/research/registry.md`](docs/research/registry.md) — collector status per agency
- [`docs/research/playbook.md`](docs/research/playbook.md) — dual-probe research method
- [`docs/schema.md`](docs/schema.md) — shared wide-column contract

## Responsible use

- Prefer official public indexes and APIs.
- Use polite delays; do not hammer agency sites.
- Respect site terms of use and robots guidance.
- This project does **not** ship CAPTCHA-solving services.
- When a host is hard-blocked (WAF), document it and use oneshot/manual harvest
  rather than fragile scheduled scrapes.

Default User-Agent identifies this project. Update the project URL in
`perb_data_collection.http.DEFAULT_USER_AGENT` when you fork.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New agencies should land a research
plan under `docs/research/agencies/` before a collector PR.

## License

MIT — see [`LICENSE`](LICENSE).
