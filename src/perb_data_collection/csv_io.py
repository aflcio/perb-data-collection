"""Wide CSV / JSONL writers for collector output."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path


def write_wide_csv(
    rows: Sequence[Mapping[str, str]],
    csv_path: Path | str,
    *,
    fieldnames: Sequence[str],
) -> int:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as outf:
        writer = csv.DictWriter(outf, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return len(rows)


def write_wide_jsonl(
    rows: Sequence[Mapping[str, str]],
    jsonl_path: Path | str,
    *,
    fieldnames: Sequence[str] | None = None,
) -> int:
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as outf:
        for row in rows:
            if fieldnames is not None:
                payload = {k: row.get(k, "") for k in fieldnames}
            else:
                payload = dict(row)
            outf.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return len(rows)
