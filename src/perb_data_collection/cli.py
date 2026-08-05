"""CLI entrypoint: ``perb-collect <slug> --out DIR``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from perb_data_collection.collectors import COLLECTORS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="perb-collect",
        description="Run a PERB / public-sector labor board collector to local wide CSV.",
    )
    parser.add_argument(
        "slug",
        nargs="?",
        help="Collector slug (e.g. dc-perb-certifications). Omit with --list.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
        help="Output directory for wide CSV (default: ./out)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available collector slugs and exit",
    )
    parser.add_argument(
        "--harvest",
        type=Path,
        default=None,
        help="Optional harvest input path (JSONL/TSV) for oneshot collectors",
    )
    args = parser.parse_args(argv)

    if args.list or not args.slug:
        for slug, meta in sorted(COLLECTORS.items()):
            print(f"{slug:40} {meta['description']}")
        if not args.slug and not args.list:
            print("\nPass a slug, or use --list.", file=sys.stderr)
            return 1
        return 0

    slug = args.slug.strip().lower().replace("_", "-")
    if slug not in COLLECTORS:
        print(f"Unknown collector: {args.slug}", file=sys.stderr)
        print("Use --list to see available slugs.", file=sys.stderr)
        return 2

    meta = COLLECTORS[slug]
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / meta["csv_name"]
    collect_fn = meta["collect"]
    kwargs: dict = {}
    if args.harvest is not None:
        kwargs["harvest_path"] = args.harvest
    count = collect_fn(out_path, **kwargs)
    print(f"Wrote {count} rows → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
