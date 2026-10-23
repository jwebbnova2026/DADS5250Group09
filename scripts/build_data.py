"""Download the 2023-2024 Boston 311 files and rebuild data/processed/.

Usage (from the repository root, with the virtual environment active):

    python scripts/build_data.py            # reuse cached downloads if present
    python scripts/build_data.py --force    # download again from data.boston.gov

You only need this to refresh the processed tables. They are committed to the
repository, so the notebook and offline mode work without running it.
"""

from __future__ import annotations

import argparse
import json

from boston311 import data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="download again even if cached")
    args = parser.parse_args()

    tables, report, sources = data.build_all(force_download=args.force)
    for src in sources:
        print(f"{src.year}: {src.size_bytes:,} bytes, md5 {src.md5}, last modified {src.last_modified}")
    for name, table in tables.items():
        print(f"wrote data/processed/{name}.csv ({len(table):,} rows)")
    print(json.dumps(report["page_check_2024"], indent=2))
    if not all(v["match"] for v in report["page_check_2024"].values()):
        print("WARNING: 2024 counts do not match the project page. See data/processed/reconciliation.json.")


if __name__ == "__main__":
    main()
