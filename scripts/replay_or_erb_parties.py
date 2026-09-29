"""Replay the OR ERB party split over a CSV of loaded rows and diff the result.

Answers "what would a re-scrape change?" without re-scraping: ``_parties`` is a
pure function of the Official Case Name, so running it over the captions that
are already loaded predicts the next load exactly.

Input is a CSV with ``row_key, case_number, native_case_type,
official_case_name, employer_name, union_name`` (the loaded values, exported
read-only from ``clrr_prod.or_erb_contentdm_order_staging``).

    uv run python scripts/replay_or_erb_parties.py captions.csv [--diff out.csv]

Run it on the commit that produced the load first: every row should come back
``same``. Any other bucket there means the harness, not the parser, is wrong.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter

from perb_data_collection.collectors.or_erb_contentdm_orders import _parties


def _bucket(old: str, new: str) -> str:
    if old == new:
        return "same"
    if not old:
        return "filled"
    if not new:
        return "emptied"
    return "changed"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("captions_csv")
    ap.add_argument("--diff", help="write every row that is not `same` to this CSV")
    args = ap.parse_args(argv)

    with open(args.captions_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    counts: Counter[tuple[str, str]] = Counter()
    nulls = Counter()
    diffs: list[dict[str, str]] = []
    for row in rows:
        employer, union = _parties(row["official_case_name"], row["native_case_type"])
        old_e, old_u = row["employer_name"].strip(), row["union_name"].strip()
        be, bu = _bucket(old_e, employer), _bucket(old_u, union)
        counts[("employer", be)] += 1
        counts[("union", bu)] += 1
        nulls["employer_null"] += not employer
        nulls["union_null"] += not union
        nulls["both_null"] += not employer and not union
        if be != "same" or bu != "same":
            diffs.append(
                {
                    "row_key": row["row_key"],
                    "case_number": row["case_number"],
                    "employer_bucket": be,
                    "union_bucket": bu,
                    "old_employer": old_e,
                    "new_employer": employer,
                    "old_union": old_u,
                    "new_union": union,
                    "official_case_name": row["official_case_name"],
                }
            )

    print(f"rows {len(rows)}")
    for side in ("employer", "union"):
        print(side, {b: counts[(side, b)] for b in ("same", "filled", "changed", "emptied")})
    print(dict(nulls))

    if args.diff:
        with open(args.diff, "w", newline="") as f:
            fields = list(diffs[0]) if diffs else ["row_key"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(diffs)
        print(f"{len(diffs)} differing rows -> {args.diff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
