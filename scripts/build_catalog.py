"""Build data/catalog/catalog.json from the processed tables.

Usage (repository root, virtual environment active):

    python scripts/build_catalog.py             # mappings only; keeps existing aliases and reviews
    python scripts/build_catalog.py --aliases   # also draft missing aliases with the LLM (live, needs a key)

Drafted aliases are saved with alias_status "provisional". A reviewer then
reads every one, edits as needed in catalog.json, and records the review in
docs/architecture.md, section 11.
"""

from __future__ import annotations

import argparse

from boston311 import catalog
from boston311.llm import LiveModel, RecordingStore, read_prompt
from boston311.schemas import AliasBatch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--aliases", action="store_true", help="draft missing aliases with the live LLM")
    parser.add_argument("--redraft", action="store_true", help="with --aliases: redraft every type, replacing existing aliases")
    args = parser.parse_args()

    entries = catalog.build_mappings()
    if catalog.CATALOG_PATH.exists():
        entries = catalog.merge_reviews(entries, list(catalog.load_catalog().values()))

    if args.aliases and args.redraft:
        for e in entries:
            e.alias_status = "missing"
    if args.aliases:
        model = LiveModel(RecordingStore())
        system = read_prompt("aliases_system")
        by_id = {e.type_id: e for e in entries}
        for batch in catalog.alias_batches(entries):
            out = model.ask("aliases", system, catalog.alias_prompt_input(batch), AliasBatch)
            for item in out.items:
                e = by_id.get(item.type_id)
                if e is None or e not in batch:
                    continue  # ignore any ID the model made up
                e.description = item.description.strip()
                e.aliases = [a.strip() for a in item.aliases if a.strip()][:8]
                e.alias_status = "provisional"
            print(f"drafted aliases for {len(out.items)} types")

    catalog.save_catalog(entries)
    mapped = sum(e.department is not None for e in entries)
    exact = sum(e.queue is not None for e in entries)
    print(f"{len(entries)} types; {mapped} department mappings; {exact} exact queue mappings")
    print(f"wrote {catalog.CATALOG_PATH} and {catalog.REVIEW_CSV_PATH}")


if __name__ == "__main__":
    main()
