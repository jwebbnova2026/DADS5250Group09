"""One-time migration of data/demo/recordings.jsonl to the v2 recording key (R4).

Run once on 2026-10-23; kept for the record.

Why: the v1 key covered the model name, prompt and catalog versions, and the
exact prompt text, but not the reasoning effort, the seed, or the response
schema. The v2 key (``boston311.llm.recording_key``) covers all of them, and
each record now stores them.

Is backfilling those settings honest? Yes, and the evidence comes from git:
* ``LLM_SEED = 5250`` was introduced in commit 2d10458, the same commit as the
  first recordings, and has never changed. ``LLM_REASONING_EFFORT = "low"``
  was introduced in 76b962d, before any recording, and has never changed.
  ``LiveModel`` has always passed both values to the model.
* ``ClassificationProposal`` (schemas.py) was last changed in f0d9c4a,
  before any recording. The alias schema's last change (``AliasDraft``) and the
  aliases-v2 drafts recorded with it were both committed in 58c311a; the drafts
  were generated after the change. Its JSON schema is byte-identical after the
  move to schemas.py.
* Every record must first prove itself: its stored key must equal the v1 key
  recomputed from the current prompts. Any record that fails is reported and
  nothing is written.

Usage: python scripts/migrate_recordings_v2.py
"""

from __future__ import annotations

import hashlib
import json

from boston311 import config, llm
from boston311.schemas import AliasBatch, ClassificationProposal

BACKFILLED_SETTINGS = {"model": "gpt-6.1-sol", "reasoning_effort": "low", "seed": 5250}
SCHEMAS = {"classify": ClassificationProposal, "aliases": AliasBatch}
PROVENANCE = (
    "seed, reasoning_effort, and schema backfilled on 2026-10-23 (migration to v2 recording keys) from git "
    "history: LLM_SEED=5250 (2d10458) and LLM_REASONING_EFFORT='low' (76b962d) never changed; response "
    "schemas unchanged since before this recording (f0d9c4a / 58c311a). Record verified against its v1 key."
)


def v1_key(kind: str, system: str, user: str) -> str:
    """The v1 key algorithm, reproduced exactly, used only to verify old records."""
    version = config.PROMPT_VERSION if kind == "classify" else config.ALIAS_PROMPT_VERSION
    blob = json.dumps([config.LLM_MODEL, version, config.CATALOG_VERSION, kind, system, user], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> None:
    if llm.generation_settings() != BACKFILLED_SETTINGS:
        raise SystemExit(f"Current settings {llm.generation_settings()} differ from the ones being backfilled; stop.")
    systems = {"classify": llm.read_prompt("classify_system"), "aliases": llm.read_prompt("aliases_system")}
    lines = [line for line in llm.RECORDINGS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    migrated, failures = [], []
    for line in lines:
        rec = json.loads(line)
        if "seed" in rec:
            raise SystemExit("Recordings already carry generation settings; migration has run before.")
        kind = rec["kind"]
        if rec["key"] != v1_key(kind, systems[kind], rec["input"]):
            failures.append(rec["key"])
            continue
        new = {
            "key": llm.recording_key(kind, systems[kind], rec["input"], SCHEMAS[kind], BACKFILLED_SETTINGS),
            "kind": kind,
            **BACKFILLED_SETTINGS,
            "schema": llm.schema_id(SCHEMAS[kind]),
            "prompt_version": llm.prompt_version(kind),
            "catalog_version": config.CATALOG_VERSION,
            "input": rec["input"],
            "output": rec["output"],
            "usage": rec.get("usage"),
            "provenance": PROVENANCE,
        }
        migrated.append(new)
    if failures:
        raise SystemExit(f"{len(failures)} record(s) failed v1 verification; nothing written: {failures[:3]}")
    tmp = llm.RECORDINGS_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in migrated:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(llm.RECORDINGS_PATH)
    print(f"migrated {len(migrated)} recordings to v2 keys; 0 failures")


if __name__ == "__main__":
    main()
