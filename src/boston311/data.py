"""Load the 2023 and 2024 Boston 311 files and turn them into planning inputs.

Spec section 4.1. The pipeline has three stages:

1. **Fetch** (``fetch_year``): ask the data.boston.gov CKAN API where a year's
   CSV lives, download it once into ``data/raw/`` and record its metadata
   (URL, size, checksum, last-modified date) for the run manifest.
2. **Load and clean** (``load_year`` and ``clean_requests``): read only the
   columns we need, remove duplicate case IDs, parse dates, and give every
   request a *target class* (valid / missing / invalid_ordering).
3. **Aggregate** (``build_processed_tables``): monthly demand, monthly type
   counts, target-class counts, target-window distributions, routing
   evidence, and service statistics. These small count tables are written to
   ``data/processed/`` and committed, so offline mode and the notebook can run
   without downloading anything.
"""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from boston311 import config

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MissingColumnError(ValueError):
    """Raised when a source file lacks a required column (spec section 5).

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

    These fields go into the run manifest (spec section 4.9) so anyone can
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
        d["path"] = self.path.relative_to(config.REPO_ROOT).as_posix()
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
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", newline="\n")
    return source


# ---------------------------------------------------------------------------
# Stage 2: load and clean
# ---------------------------------------------------------------------------

# Target classes (spec section 4.3). Every historical request falls in exactly
# one of these, decided by comparing the *calendar dates* of its target and
# open timestamps (time of day is ignored):
#   valid            - has a target date on or after the open date
#   missing          - has no target date at all
#   invalid_ordering - target date is before the open date (a data error)
TARGET_VALID = "valid"
TARGET_MISSING = "missing"
TARGET_INVALID = "invalid_ordering"
TARGET_CLASSES: tuple[str, ...] = (TARGET_VALID, TARGET_MISSING, TARGET_INVALID)


def check_columns(path: Path) -> None:
    """Fail early, naming the column, if a source CSV lacks a required column.

    Reads only the header row, so it is fast even for a 180 MB file.
    """
    header = pd.read_csv(path, nrows=0).columns
    missing = [c for c in config.REQUIRED_COLUMNS if c not in header]
    if missing:
        raise MissingColumnError(f"{path.name} is missing required column(s): {', '.join(missing)}")


def load_year(path: Path) -> pd.DataFrame:
    """Read one raw CSV with only the columns we use, every department included.

    All columns are read as text first (``dtype=str``) so that pandas never
    guesses a type and silently changes a value, for example by turning the
    case ID ``"101005236041"`` into a float. Only truly empty cells become
    missing values. Dates are parsed afterwards in :func:`clean_requests`.
    """
    check_columns(path)
    return pd.read_csv(
        path,
        usecols=list(config.REQUIRED_COLUMNS) + ["on_time"],
        dtype=str,
        keep_default_na=False,  # do not treat strings like "NA" as missing...
        na_values=[""],  # ...only truly empty cells
    )


def clean_requests(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Deduplicate, parse dates, and add the target class and window.

    This works on *all* departments, because the catalog needs out-of-scope
    rows to compute routing shares correctly. Filtering to the four
    departments happens in :func:`in_scope`.

    Returns:
        (clean, counts): the cleaned table and a dict of how many rows were
        removed at each step, for the reconciliation report.
    """
    counts: dict[str, int] = {"rows_read": int(len(raw))}
    df = raw.copy()

    # 1. Deduplicate by case ID, keeping the first occurrence. (The audit
    #    found no duplicates, but the check runs on every load.)
    before = len(df)
    df = df.drop_duplicates(subset="case_enquiry_id", keep="first")
    counts["duplicates_removed"] = int(before - len(df))

    # 2. Parse timestamps. The files mix "2024-01-04 10:43:17.097" and
    #    "2024-01-04 10:43:17", so we ask for general ISO 8601 parsing.
    #    Timestamps are Boston local time (project page); we keep them as-is
    #    with no time-zone conversion, because only calendar dates matter.
    for col in ("open_dt", "sla_target_dt", "closed_dt"):
        df[col] = pd.to_datetime(df[col], format="ISO8601", errors="coerce")
    # A request with no usable open date cannot be placed in any month.
    bad_open = df["open_dt"].isna()
    counts["unparseable_open_dt_removed"] = int(bad_open.sum())
    df = df[~bad_open].copy()

    # 3. Calendar dates and the target window in whole days. A same-day
    #    target has window 0. Requests with no target get NaN.
    df["open_date"] = df["open_dt"].dt.normalize()
    df["target_date"] = df["sla_target_dt"].dt.normalize()
    df["window_days"] = (df["target_date"] - df["open_date"]).dt.days

    # 4. Target class, following the table in spec section 4.3.
    df["target_class"] = np.select(
        [df["target_date"].isna(), df["window_days"] < 0],
        [TARGET_MISSING, TARGET_INVALID],
        default=TARGET_VALID,
    )

    # 5. Convenience columns used by the aggregations.
    df["year"] = df["open_dt"].dt.year
    df["month"] = df["open_dt"].dt.month
    # Days from opening to closing, as a fraction (NaN if still open).
    df["days_to_close"] = (df["closed_dt"] - df["open_dt"]).dt.total_seconds() / 86_400
    # HTML entities such as "&amp;" appear in free-text fields (project page,
    # "Things to watch for"); decode them so "A &amp; B" reads "A & B".
    df["case_title"] = df["case_title"].map(lambda s: html.unescape(s).strip() if isinstance(s, str) else s)
    return df, counts


def in_scope(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the four planning departments (PWDx, BTDT, PARK, ISD)."""
    return df[df["department"].isin(config.DEPT_CODES)].copy()


def harmonize_neighborhood(series: pd.Series) -> pd.Series:
    """Apply ``config.NEIGHBORHOOD_ALIASES`` and label blanks "Unspecified"."""
    return series.fillna(config.UNSPECIFIED_NEIGHBORHOOD).replace(config.NEIGHBORHOOD_ALIASES)


# ---------------------------------------------------------------------------
# Stage 3: aggregate into small committed tables
# ---------------------------------------------------------------------------


def build_type_ids(scope: pd.DataFrame) -> pd.DataFrame:
    """Give every in-scope request type a stable short ID like ``T001``.

    IDs follow alphabetical order of the type name, so they never depend on
    row order in the source file. The spec's rounding rules break ties "to
    the lower type ID", which is why the order has to be stable.
    """
    names = sorted(scope["type"].dropna().unique())
    return pd.DataFrame({"type_id": [f"T{i + 1:03d}" for i in range(len(names))], "type": names})


def build_processed_tables(all_rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute every derived table the rest of the package needs.

    Args:
        all_rows: cleaned 2023 + 2024 requests from *all* departments.

    Returns:
        A dict mapping a table name to a DataFrame. Each is saved as
        ``data/processed/<name>.csv``. Every table holds counts, not
        individual requests, so the files are small and safe to commit.
    """
    scope = in_scope(all_rows)
    types = build_type_ids(scope)
    scope = scope.merge(types, on="type", how="left")
    tables: dict[str, pd.DataFrame] = {"types": types}

    # Monthly demand per department and year (input to the forecast).
    tables["monthly_demand"] = (
        scope.groupby(["department", "year", "month"]).size().rename("requests").reset_index()
    )

    # Monthly request counts per department and type. The 2024 rows give the
    # "same-month type shares" used to split each forecast month into types.
    tables["type_month_counts"] = (
        scope.groupby(["department", "type_id", "year", "month"]).size().rename("requests").reset_index()
    )

    # Target-class counts per department and type, 2023-2024 combined. Every
    # class appears as a column (0 where absent), so shares are easy to read.
    tc = scope.groupby(["department", "type_id", "target_class"]).size().unstack(fill_value=0)
    for cls in TARGET_CLASSES:
        if cls not in tc.columns:
            tc[cls] = 0
    tables["target_class_counts"] = tc[list(TARGET_CLASSES)].reset_index()

    # Distribution of valid target windows: how many requests had a window of
    # 0 days, 1 day, 2 days, ... per department and type, 2023-2024 combined.
    valid = scope[scope["target_class"] == TARGET_VALID]
    tables["window_counts"] = (
        valid.groupby(["department", "type_id", "window_days"])
        .size()
        .rename("requests")
        .reset_index()
        .astype({"window_days": int})
    )

    # Routing evidence for the catalog: for every in-scope type, how many of
    # its requests (in ALL departments, including out-of-scope ones) went to
    # each department and queue. Shares must use all departments, otherwise a
    # type mostly handled elsewhere would look 100% in-scope (spec 4.6).
    routed = all_rows[all_rows["type"].isin(types["type"])].merge(types, on="type")
    tables["type_queue_counts"] = (
        routed.groupby(["type_id", "department", "queue"]).size().rename("requests").reset_index()
    )

    # Historical service statistics per type (shown to residents labeled as
    # "historical", spec 4.6), over the four departments only.
    tables["type_service_stats"] = _service_stats(scope, ["type_id"])

    # The most common case titles per type, used only as context when drafting
    # aliases (spec 4.6). We keep the top 10 per type, and only titles used at
    # least 3 times: rarer titles are mostly one-off typing or internal codes
    # and add noise rather than useful wording.
    titles = scope.dropna(subset=["case_title"]).groupby(["type_id", "case_title"]).size().rename("requests")
    titles = titles[titles >= 3]
    tables["type_titles"] = (
        titles.reset_index()
        .sort_values(["type_id", "requests", "case_title"], ascending=[True, False, True])
        .groupby("type_id")
        .head(10)
        .reset_index(drop=True)
    )

    # Neighborhood equity inputs (deliverable 6): the same service statistics
    # per department x neighborhood, plus per department x neighborhood x type
    # so the analysis can adjust for each neighborhood's mix of request types.
    scope["neighborhood"] = harmonize_neighborhood(scope["neighborhood"])
    tables["neighborhood_stats"] = _service_stats(scope, ["department", "neighborhood"])
    tables["neighborhood_type_stats"] = _service_stats(
        scope, ["department", "neighborhood", "type_id"], with_median=False
    )
    return tables


def _service_stats(df: pd.DataFrame, keys: list[str], *, with_median: bool = True) -> pd.DataFrame:
    """Count requests and on-time outcomes per group.

    On-time uses the city's own ``on_time`` flag, counted only over requests
    with a valid target date. The city flags every request *without* a
    target as ONTIME, so including them would overstate on-time service.

    Output columns:
        requests             - all requests in the group
        with_target          - requests with a valid target date
        on_time              - of those, how many the city flagged ONTIME
        closed               - requests that have a close date
        median_days_to_close - median over closed requests (if with_median)
    """
    has_target = df["target_class"] == TARGET_VALID
    out = df.assign(
        _with_target=has_target,
        _on_time=has_target & (df["on_time"] == "ONTIME"),
        _closed=df["closed_dt"].notna(),
    )
    agg = out.groupby(keys).agg(
        requests=("case_enquiry_id", "size"),
        with_target=("_with_target", "sum"),
        on_time=("_on_time", "sum"),
        closed=("_closed", "sum"),
    )
    if with_median:
        agg["median_days_to_close"] = out[out["_closed"]].groupby(keys)["days_to_close"].median().round(2)
    return agg.reset_index()


def reconciliation_report(all_rows: pd.DataFrame, counts_by_year: dict[int, dict]) -> dict:
    """Summarize what was loaded, removed, and kept (spec section 4.1).

    Includes the comparison of our 2024 counts against the project page's
    stated totals. A mismatch does not stop the pipeline, but it is reported
    and the reconciliation test fails, so nobody misses it.
    """
    scope = in_scope(all_rows)
    report: dict = {"by_year": {}, "page_check_2024": {}}
    for year, counts in counts_by_year.items():
        rows = all_rows[all_rows["year"] == year]
        kept = scope[scope["year"] == year]
        report["by_year"][str(year)] = {
            **counts,
            "rows_after_cleaning": int(len(rows)),
            "out_of_scope_departments_excluded": int(len(rows) - len(kept)),
            "in_scope_rows": int(len(kept)),
            "in_scope_by_department": {d: int((kept["department"] == d).sum()) for d in config.DEPT_CODES},
            "target_classes": {c: int((kept["target_class"] == c).sum()) for c in TARGET_CLASSES},
        }
    kept24 = scope[scope["year"] == 2024]
    for code, dept in config.DEPARTMENTS.items():
        ours = int((kept24["department"] == code).sum())
        report["page_check_2024"][code] = {"page": dept.requests_2024, "ours": ours, "match": ours == dept.requests_2024}
    return report


def build_all(*, force_download: bool = False) -> tuple[dict[str, pd.DataFrame], dict, list[SourceFile]]:
    """Run the whole data pipeline: fetch, clean, aggregate, and save.

    This is what ``scripts/build_data.py`` calls. It needs network access the
    first time (to download about 370 MB); later runs reuse the cached files.
    """
    sources, frames, counts_by_year = [], [], {}
    for year in config.DATA_YEARS:
        src = fetch_year(year, force=force_download)
        sources.append(src)
        clean, counts = clean_requests(load_year(src.path))
        # Each file should contain only requests opened in its own year. Rows
        # opened in another year are dropped and counted, so data from one
        # year can never leak into another year's totals.
        wrong_year = clean["year"] != year
        counts["opened_outside_file_year_removed"] = int(wrong_year.sum())
        frames.append(clean[~wrong_year])
        counts_by_year[year] = counts
    all_rows = pd.concat(frames, ignore_index=True)

    # Spec check 5: nothing after the training cutoff may reach the forecast.
    cutoff_end = pd.Timestamp(config.TRAINING_CUTOFF) + pd.Timedelta(days=1)
    if all_rows["open_dt"].max() >= cutoff_end:
        raise DataSourceError("Loaded data contains requests after the training cutoff")

    tables = build_processed_tables(all_rows)
    report = reconciliation_report(all_rows, counts_by_year)
    report["sources"] = [s.to_dict() for s in sources]
    save_processed(tables, report)
    return tables, report, sources


def save_processed(tables: dict[str, pd.DataFrame], report: dict) -> None:
    """Write each table to ``data/processed/<name>.csv`` plus the report JSON."""
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        # lineterminator="\n" keeps files byte-identical on Windows and macOS.
        table.to_csv(config.PROCESSED_DIR / f"{name}.csv", index=False, lineterminator="\n")
    (config.PROCESSED_DIR / "reconciliation.json").write_text(json.dumps(report, indent=2) + "\n", newline="\n")


def load_processed(name: str) -> pd.DataFrame:
    """Read one committed table from ``data/processed/`` (no network needed)."""
    path = config.PROCESSED_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python scripts/build_data.py` once to create it.")
    return pd.read_csv(path, dtype={"type_id": str, "department": str}, keep_default_na=False, na_values=[""])


def load_reconciliation() -> dict:
    """Read the committed reconciliation report."""
    return json.loads((config.PROCESSED_DIR / "reconciliation.json").read_text())
