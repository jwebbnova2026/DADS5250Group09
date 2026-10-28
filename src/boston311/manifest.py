"""One JSON run manifest per run (spec section 4.9).

A manifest records everything needed to check or reproduce a run:

* **sources** - the raw files' download URLs, last-modified dates, sizes,
  and checksums (from the data pipeline's reconciliation report);
* **inputs** - SHA-256 checksums of every committed input the run read
  (processed tables, catalog, eval sets, prompts, recordings);
* **parameters** - every constant in ``config`` (GIVEN rules and DEFAULTs),
  including the training cutoff and the scenario seeds;
* **model** - model ID, reasoning effort, seed, prompt and catalog versions;
* **mode** - live or offline;
* **environment** - Python and key package versions, and the git commit;
* **outputs** - the files the run wrote.

Manifests are written to ``outputs/manifests/run_<UTC timestamp>.json``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from boston311 import config
from boston311.data import load_reconciliation

PACKAGES = ("pandas", "numpy", "scikit-learn", "pydantic", "langchain", "langchain-core", "langchain-openai", "langgraph", "openai")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.resolve().relative_to(config.REPO_ROOT).as_posix()


def _jsonable(value):
    """Make config values JSON-friendly (Fractions, sets, dataclasses...)."""
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, Path):
        return _rel(value)
    if hasattr(value, "__dataclass_fields__"):
        return {k: _jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    return value


def config_snapshot() -> dict:
    """Every UPPER_CASE constant in boston311.config."""
    return {k: _jsonable(getattr(config, k)) for k in dir(config) if k.isupper() and not k.endswith("_DIR") and k != "REPO_ROOT"}


def input_files() -> list[Path]:
    """The committed inputs every run depends on."""
    files = sorted(config.PROCESSED_DIR.glob("*.csv")) + [config.PROCESSED_DIR / "reconciliation.json"]
    files += sorted(config.CATALOG_DIR.glob("*")) + sorted(config.EVAL_DIR.glob("*.jsonl")) + sorted(config.PROMPTS_DIR.glob("*.txt"))
    files += sorted(config.DEMO_DIR.glob("*.jsonl"))
    return [f for f in files if f.is_file()]


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "") if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def build_manifest(mode: str, outputs: list[Path], extra: dict | None = None) -> dict:
    """Assemble the manifest dict for one run."""
    versions = {}
    for p in PACKAGES:
        try:
            versions[p] = version(p)
        except PackageNotFoundError:
            versions[p] = None
    recon = load_reconciliation()
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "sources": recon.get("sources", []),
        "data_reconciliation": {"page_check_2024": recon["page_check_2024"], "by_year": recon["by_year"]},
        "training_cutoff": config.TRAINING_CUTOFF,
        "seeds": {"planning": config.PLANNING_SEED, "evaluation": config.EVALUATION_SEED},
        "model": {
            "provider": config.LLM_PROVIDER,
            "id": config.LLM_MODEL,
            "reasoning_effort": config.LLM_REASONING_EFFORT,
            "seed": config.LLM_SEED,
            "prompt_version": config.PROMPT_VERSION,
            "alias_prompt_version": config.ALIAS_PROMPT_VERSION,
            "catalog_version": config.CATALOG_VERSION,
        },
        "parameters": config_snapshot(),
        "inputs": {_rel(f): _sha256(f) for f in input_files()},
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "packages": versions, "git_commit": git_commit()},
        "outputs": [_rel(p) for p in outputs],
        **(extra or {}),
    }


def write_manifest(manifest: dict) -> Path:
    """Write a manifest to outputs/manifests/ and return its path.

    The file name comes from the creation time. If two runs start in the
    same second, a counter is added, so a manifest is never overwritten (one
    manifest per run, spec 4.9). Run manifests are gitignored; only
    ``outputs/manifests/reference_run_all.json``, describing the committed
    outputs, is kept in git.
    """
    folder = config.OUTPUTS_DIR / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = manifest["created_utc"].replace(":", "").replace("-", "").replace("+0000", "Z")
    path = folder / f"run_{stamp}.json"
    n = 1
    while path.exists():
        n += 1
        path = folder / f"run_{stamp}_{n}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
