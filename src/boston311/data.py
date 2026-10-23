"""Load the 2023 and 2024 Boston 311 files and turn them into planning inputs.

Spec section 5.1. The pipeline has three stages:

1. **Fetch** (``fetch_year``): ask the data.boston.gov CKAN API where a year's
   CSV lives, download it once into ``data/raw/`` and record its metadata
   (URL, size, checksum, last-modified date) for the run manifest.
2. **Load and clean** (``load_requests``): read only the columns we need,
   keep the four in-scope departments, remove duplicate case IDs, parse dates,
   and give every request a *target class* (valid / missing /
   invalid_ordering).
3. **Aggregate** (later functions): monthly demand, monthly type shares,
   target-class shares, and target-window distributions. These small tables
   are written to ``data/processed/`` and committed, so offline mode and the
   notebook can run without downloading anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from boston311 import config

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MissingColumnError(ValueError):
    """Raised when a source file lacks a required column (spec section 6).

    The message names the missing column(s) so the cause is obvious.
    """


class DataSourceError(RuntimeError):
    """Raised when the CKAN API or a download does not behave as expected."""


# ---------------------------------------------------------------------------
# Stage 1: fetch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceFile:
    """Where one year's raw CSV came from and what we got.

    These fields go into the run manifest (spec section 5.9) so anyone can
    check that a rerun used byte-for-byte the same input.
    """

    year: int
    resource_id: str
    url: str
    path: Path
    size_bytes: int
    md5: str  # checksum CKAN publishes for the file; we verify against it
    sha256: str  # stronger checksum we compute ourselves for the manifest
    last_modified: str  # when the city last changed the file, per CKAN
    retrieved_at: str  # when we downloaded it (UTC, ISO 8601)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["path"] = str(self.path.relative_to(config.REPO_ROOT))
        return d


def _ckan_resource_metadata(resource_id: str) -> dict:
    """Call CKAN's ``resource_show`` endpoint and return the resource record."""
    url = f"{config.CKAN_API_BASE}/resource_show"
    resp = requests.get(url, params={"id": resource_id}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    # CKAN wraps every answer as {"success": bool, "result": {...}}.
    if not payload.get("success"):
        raise DataSourceError(f"CKAN resource_show failed for {resource_id}: {payload}")
    return payload["result"]


def _file_hashes(path: Path) -> tuple[str, str]:
    """Return (md5, sha256) of a file, reading it in 1 MB chunks to save memory."""
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def fetch_year(year: int, *, force: bool = False) -> SourceFile:
    """Make sure the raw CSV for ``year`` is on disk and describe it.

    If the file was downloaded before, we reuse it (no network needed) and
    read its saved metadata. Otherwise we ask the CKAN API for the download
    URL, stream the file to ``data/raw/311_<year>.csv``, and verify its MD5
    checksum against the one CKAN publishes.

    Args:
        year: 2023 or 2024 (the keys of ``config.RESOURCE_IDS``).
        force: Download again even if a cached copy exists.

    Returns:
        A :class:`SourceFile` describing the file.
    """
    if year not in config.RESOURCE_IDS:
        raise ValueError(f"No pinned resource for year {year}; expected one of {sorted(config.RESOURCE_IDS)}")
    resource_id = config.RESOURCE_IDS[year]
    csv_path = config.RAW_DIR / f"311_{year}.csv"
    meta_path = config.RAW_DIR / f"311_{year}.meta.json"

    # Cached copy: trust it only if both the CSV and its metadata exist.
    if csv_path.exists() and meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
        meta["path"] = csv_path
        return SourceFile(**meta)

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    record = _ckan_resource_metadata(resource_id)
    url = record["url"]

    # Stream to a temporary name first, so an interrupted download never
    # leaves a half-written file that looks complete.
    tmp_path = csv_path.with_suffix(".csv.part")
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with tmp_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)

    md5, sha256 = _file_hashes(tmp_path)
    published_md5 = record.get("hash") or ""
    if published_md5 and published_md5 != md5:
        tmp_path.unlink()
        raise DataSourceError(
            f"Downloaded {year} file does not match the checksum CKAN publishes "
            f"(got md5 {md5}, expected {published_md5}). Try again later."
        )
    tmp_path.replace(csv_path)

    source = SourceFile(
        year=year,
        resource_id=resource_id,
        url=url,
        path=csv_path,
        size_bytes=csv_path.stat().st_size,
        md5=md5,
        sha256=sha256,
        last_modified=record.get("last_modified") or "",
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    meta = source.to_dict()
    meta.pop("path")
    meta_path.write_text(json.dumps(meta, indent=2))
    return source
