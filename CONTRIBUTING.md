# Contributing

## Research first

For a new agency:

1. Add or update `docs/research/agencies/<slug>.md` using the playbook in
   `docs/research/playbook.md`.
2. Update `docs/research/registry.md` with status and last-verified date.
3. Only then open a collector PR.

## Collectors

- Emit wide CSV via `perb_data_collection.csv_io.write_wide_csv`.
- Populate shared core columns from `docs/schema.md` when the source has them.
- Agency-specific columns are welcome.
- Prefer stdlib `urllib` (`perb_data_collection.http`). Use Playwright only when
  documented as required (`pip install '.[browser]'`).
- Add fixture-based unit tests under `tests/`. Do not hit live network in CI.

## Code style

- Python 3.12+, type hints, dataclasses over TypedDict.
- No warehouse, geocoding, or private pipeline glue in this repo.
