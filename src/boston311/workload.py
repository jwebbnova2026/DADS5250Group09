"""Seeded synthetic 2025 workloads, including coupled sensitivity scenarios.

Spec section 5.3. A *workload* is the full list of requests for 2025: for
each request its department, type, arrival day, target class, and target day.
The simulator then serves this list.

Three ideas make the workloads trustworthy and repeatable:

1. **Deterministic arrivals.** How many requests of each type arrive on each
   day is computed by exact integer rounding (largest remainder, below) from
   the forecast and the 2024 type mix. No randomness is involved, so every
   workload built from the same forecast has identical arrival counts.

2. **Seeded attributes.** Only the target class and target window of each
   request are random, drawn from the 2023-2024 history with a seeded random
   number generator. Two independent seeds (config.PLANNING_SEED and
   config.EVALUATION_SEED) give two independent *streams*:
   * the **planning workload** - the only one the planner ever sees;
   * the **base evaluation workload** - used to score the frozen plan.
   Rebuilding a workload from the same seed reproduces it exactly.

3. **Coupled scenarios.** The +20%, -20%, and snowstorm workloads are built
   *from the base evaluation workload*: they only add new requests or remove
   existing ones, never change a kept request. So any difference between
   scenarios comes from the demand change alone, not from re-drawn random
   attributes.

Largest-remainder rounding
--------------------------
To split an integer total N across items with integer weights w_i so the
parts are whole numbers that add up to exactly N:

1. Give each item floor(N * w_i / W), where W is the sum of the weights.
2. Hand the few leftover units, one each, to the items with the largest
   remainders (N * w_i mod W), breaking ties toward the earlier item.

Everything is integer arithmetic, so there is no floating-point error.
Example from the spec: weights [1, 3, 7] split 5 as [1, 1, 3] but split 6 as
[0, 2, 4], so recomputing a split for a bigger total can *shrink* a cell. That
is why scenarios never recompute the base split: they allocate only the extra
(or removed) requests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

import numpy as np
import pandas as pd

from boston311 import config
from boston311.data import TARGET_CLASSES, TARGET_INVALID, TARGET_MISSING, TARGET_VALID, load_processed
from boston311.simulate import Calendar, Requests, build_calendar

# Sub-stream labels for the extra requests of each scenario. Each scenario's
# extras get their own generator derived from the evaluation seed, so adding
# a scenario never changes the base workload's random draws.
_EXTRA_STREAM_KEYS = {"plus20": 1, "spike": 2}

# Column order of every workload table.
WORKLOAD_COLUMNS = ["seq", "department", "type_id", "arrival_day", "target_class", "window_days", "target_day"]


# ---------------------------------------------------------------------------
# Exact rounding helpers
# ---------------------------------------------------------------------------


def largest_remainder(total: int, weights: Sequence[int]) -> list[int]:
    """Split ``total`` into whole parts proportional to integer ``weights``.

    Ties in the remainder go to the earlier item (lower index), so callers
    must pass weights in their tie-break order (lower type ID first, or
    earlier day first). The parts always sum to exactly ``total``.

    >>> largest_remainder(5, [1, 3, 7])
    [1, 1, 3]
    >>> largest_remainder(6, [1, 3, 7])
    [0, 2, 4]
    """
    if total < 0:
        raise ValueError("total cannot be negative")
    weights = [int(w) for w in weights]
    if any(w < 0 for w in weights):
        raise ValueError("weights cannot be negative")
    w_sum = sum(weights)
    if w_sum == 0:
        if total == 0:
            return [0] * len(weights)
        raise ValueError("cannot split a positive total over all-zero weights")
    parts = [total * w // w_sum for w in weights]
    remainders = [total * w % w_sum for w in weights]
    leftover = total - sum(parts)
    # Sort by remainder, largest first; for equal remainders, lower index first.
    for i in sorted(range(len(weights)), key=lambda i: (-remainders[i], i))[:leftover]:
        parts[i] += 1
    return parts


def round_half_up(x: Fraction) -> int:
    """Round an exact fraction to the nearest integer, halves going up.

    Python's built-in ``round`` sends halves to the nearest *even* number
    (round(2.5) == 2), which would be surprising in a report, so we do it
    explicitly. Example: 1,557 x 4/5 = 1,245.6 -> 1,246.
    """
    return math.floor(x + Fraction(1, 2))


# ---------------------------------------------------------------------------
# Historical inputs the generator needs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class History:
    """The historical tables workload generation reads (all from data/processed).

    Attributes:
        type_month_2024: 2024 request counts per (department, type_id, month);
            these are the "same-month type shares".
        class_counts: target-class counts per (department, type_id), 2023-2024.
        windows: valid target-window counts per (department, type_id,
            window_days), 2023-2024.
    """

    type_month_2024: pd.DataFrame
    class_counts: pd.DataFrame
    windows: pd.DataFrame

    @classmethod
    def load(cls) -> "History":
        tmc = load_processed("type_month_counts")
        return cls(
            type_month_2024=tmc[tmc["year"] == 2024].drop(columns="year"),
            class_counts=load_processed("target_class_counts"),
            windows=load_processed("window_counts"),
        )


class WindowSampler:
    """Draws target windows using the spec's fallback chain (spec 5.3).

    For a request of type T in department D:
    1. use T's own valid windows if T has at least 50 of them;
    2. otherwise D's pooled valid windows, if D has at least 50;
    3. otherwise the pooled valid windows of all four departments;
    4. if even that pool were empty, the request becomes no-target and a
       warning is recorded (not expected with real data).
    """

    def __init__(self, windows: pd.DataFrame, min_samples: int = config.MIN_WINDOW_SAMPLES):
        self.min_samples = min_samples
        self._type: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        for (dept, tid), g in windows.groupby(["department", "type_id"]):
            self._type[(dept, tid)] = (g["window_days"].to_numpy(), g["requests"].to_numpy())
        self._dept: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for dept, g in windows.groupby("department"):
            s = g.groupby("window_days")["requests"].sum()
            self._dept[dept] = (s.index.to_numpy(), s.to_numpy())
        s = windows.groupby("window_days")["requests"].sum()
        self._pooled = (s.index.to_numpy(), s.to_numpy())
        self.warnings: list[str] = []

    def source_for(self, dept: str, type_id: str) -> tuple[str, tuple[np.ndarray, np.ndarray] | None]:
        """Which distribution a type uses: ("type"|"department"|"pooled"|"none", (values, counts))."""
        own = self._type.get((dept, type_id))
        if own is not None and own[1].sum() >= self.min_samples:
            return "type", own
        d = self._dept.get(dept)
        if d is not None and d[1].sum() >= self.min_samples:
            return "department", d
        if self._pooled[1].sum() > 0:
            return "pooled", self._pooled
        return "none", None

    def draw(self, rng: np.random.Generator, dept: str, type_id: str, n: int) -> np.ndarray | None:
        """Draw ``n`` windows (in days), or None if no distribution exists."""
        source, dist = self.source_for(dept, type_id)
        if dist is None:
            self.warnings.append(f"No valid windows for {dept}/{type_id}; requests made no-target")
            return None
        values, counts = dist
        return rng.choice(values, size=n, p=counts / counts.sum())


# ---------------------------------------------------------------------------
# Arrival counts (deterministic)
# ---------------------------------------------------------------------------


def type_weights(history: History, dept: str, month: int) -> pd.DataFrame:
    """2024 same-month counts of each type in a department, sorted by type ID."""
    tm = history.type_month_2024
    w = tm[(tm["department"] == dept) & (tm["month"] == month)].sort_values("type_id")
    return w[["type_id", "requests"]].reset_index(drop=True)


def allocate_to_cells(total: int, history: History, dept: str, month: int, days: Sequence[int]) -> list[tuple[str, int, int]]:
    """Split a department-month total into (type_id, day, count) cells.

    Step 1 splits the total across types by 2024 same-month type counts.
    Step 2 splits each type's count uniformly across ``days`` (earliest day
    first on ties). Both steps use largest-remainder rounding, so the cell
    counts add up to exactly ``total``. Zero cells are omitted.
    """
    w = type_weights(history, dept, month)
    per_type = largest_remainder(total, w["requests"].tolist())
    cells = []
    for type_id, n_type in zip(w["type_id"], per_type):
        for day, n in zip(days, largest_remainder(n_type, [1] * len(days))):
            if n:
                cells.append((type_id, day, n))
    return cells


# ---------------------------------------------------------------------------
# Building workloads
# ---------------------------------------------------------------------------


@dataclass
class Workload:
    """A named list of 2025 requests, one row per request.

    ``requests`` columns:
        seq          - unique generation sequence number (FIFO tie-breaker)
        department   - department code
        type_id      - request type ID (see data/processed/types.csv)
        arrival_day  - day index (0 = January 1, 2025)
        target_class - "valid", "missing", or "invalid_ordering"
        window_days  - target window in days (-1 for no-target requests)
        target_day   - arrival_day + window_days (-1 for no-target requests)
    """

    name: str
    requests: pd.DataFrame
    window_sources: dict[tuple[str, str], str]
    warnings: list[str]

    def for_department(self, dept: str) -> Requests:
        """The simulator's view of one department: arrays in FIFO order."""
        df = self.requests[self.requests["department"] == dept].sort_values(["arrival_day", "seq"])
        return Requests(
            arrival_day=df["arrival_day"].to_numpy(np.int64),
            has_target=(df["target_class"] == TARGET_VALID).to_numpy(),
            target_day=df["target_day"].to_numpy(np.int64),
            seq=df["seq"].to_numpy(np.int64),
        )

    def monthly_totals(self, calendar: Calendar) -> pd.DataFrame:
        """Requests per department and month (for reconciliation checks)."""
        month = calendar.month_of_day[self.requests["arrival_day"].to_numpy()]
        return self.requests.assign(month=month).groupby(["department", "month"]).size().rename("requests").reset_index()


def _draw_attributes(
    cells: pd.DataFrame, rng: np.random.Generator, history: History, sampler: WindowSampler
) -> pd.DataFrame:
    """Give every request a target class and (if valid) a window.

    ``cells`` has one row per request, already in generation order. Requests
    are processed type by type (department order, then type ID), each type's
    requests in generation order, so the draws are fully determined by the
    seed. For each request we first draw its class from its type's
    historical class shares; only valid requests then get a window.
    """
    cc = history.class_counts.set_index(["department", "type_id"])
    target_class = np.empty(len(cells), dtype=object)
    window = np.full(len(cells), -1, dtype=np.int64)
    for dept in config.DEPT_CODES:
        dept_mask = (cells["department"] == dept).to_numpy()
        for type_id in sorted(cells.loc[dept_mask, "type_id"].unique()):
            idx = np.flatnonzero(dept_mask & (cells["type_id"] == type_id).to_numpy())
            counts = cc.loc[(dept, type_id), list(TARGET_CLASSES)].to_numpy(dtype=float)
            classes = rng.choice(np.array(TARGET_CLASSES, dtype=object), size=len(idx), p=counts / counts.sum())
            target_class[idx] = classes
            valid_idx = idx[classes == TARGET_VALID]
            if len(valid_idx):
                drawn = sampler.draw(rng, dept, type_id, len(valid_idx))
                if drawn is None:
                    target_class[valid_idx] = TARGET_MISSING  # fallback step 4
                else:
                    window[valid_idx] = drawn
    out = cells.copy()
    out["target_class"] = target_class
    out["window_days"] = window
    out["target_day"] = np.where(window >= 0, out["arrival_day"].to_numpy() + window, -1)
    return out


def _expand_cells(cells: list[tuple[str, str, int, int]], first_seq: int) -> pd.DataFrame:
    """Turn (department, type_id, day, count) cells into one row per request.

    Requests get consecutive sequence numbers starting at ``first_seq``, in
    the order department -> day -> type ID. Within a day, requests are
    therefore served in type-ID order (the FIFO tie-break).
    """
    cells = sorted(cells, key=lambda c: (config.DEPT_CODES.index(c[0]), c[2], c[1]))
    rows = [(dept, tid, day) for dept, tid, day, n in cells for _ in range(n)]
    df = pd.DataFrame(rows, columns=["department", "type_id", "arrival_day"])
    df.insert(0, "seq", np.arange(first_seq, first_seq + len(df), dtype=np.int64))
    return df


def build_base_workload(
    forecast: pd.DataFrame,
    seed: int,
    name: str,
    *,
    history: History | None = None,
    calendar: Calendar | None = None,
) -> Workload:
    """Build a workload from the forecast with one random stream.

    Call it with ``config.PLANNING_SEED`` for the planning workload and with
    ``config.EVALUATION_SEED`` for the base evaluation workload.

    Args:
        forecast: columns department, month, forecast (integer counts).
        seed: the stream's seed.
        name: label stored on the workload ("planning", "base", ...).
    """
    history = history or History.load()
    calendar = calendar or build_calendar()
    cells: list[tuple[str, str, int, int]] = []
    for dept in config.DEPT_CODES:
        for month in range(1, 13):
            row = forecast[(forecast["department"] == dept) & (forecast["month"] == month)]
            total = int(round_half_up(Fraction(int(row["forecast"].iloc[0]))))  # spec: rounded to an integer
            days = list(calendar.month_days(month))
            cells += [(dept, t, d, n) for t, d, n in allocate_to_cells(total, history, dept, month, days)]
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    sampler = WindowSampler(history.windows)
    reqs = _draw_attributes(_expand_cells(cells, first_seq=0), rng, history, sampler)
    sources = {
        (d, t): sampler.source_for(d, t)[0] for d, t in reqs[["department", "type_id"]].drop_duplicates().itertuples(index=False)
    }
    return Workload(name, reqs[WORKLOAD_COLUMNS], sources, sampler.warnings)


def _add_extras(
    base: Workload, extra_cells: list[tuple[str, str, int, int]], stream_key: int, name: str, history: History
) -> Workload:
    """Return a new workload = every base request unchanged + extra requests.

    Extra requests get sequence numbers after the largest base number, so on
    any given day they queue behind that day's base requests. Their
    attributes come from a dedicated sub-stream of the evaluation stream.
    """
    first_seq = int(base.requests["seq"].max()) + 1 if len(base.requests) else 0
    rng = np.random.default_rng(np.random.SeedSequence([config.EVALUATION_SEED, stream_key]))
    sampler = WindowSampler(history.windows)
    extras = _draw_attributes(_expand_cells(extra_cells, first_seq), rng, history, sampler) if extra_cells else None
    parts = [base.requests] + ([extras[WORKLOAD_COLUMNS]] if extras is not None else [])
    combined = pd.concat(parts, ignore_index=True)
    return Workload(name, combined, base.window_sources, base.warnings + sampler.warnings)


def build_plus_scenario(base: Workload, factor: Fraction, name: str, *, history: History, calendar: Calendar) -> Workload:
    """+20% scenario: keep every base request, add the extra requests.

    For each department-month, the scenario total is the base total times
    ``factor``, rounded half up. Only the difference (scenario total minus
    base total) is allocated, across types and days with the same
    largest-remainder rules as the base, so no cell can shrink.
    """
    month = calendar.month_of_day[base.requests["arrival_day"].to_numpy()]
    base_tot = base.requests.assign(month=month).groupby(["department", "month"]).size()
    extra_cells = []
    for dept in config.DEPT_CODES:
        for m in range(1, 13):
            b = int(base_tot.get((dept, m), 0))
            extra = round_half_up(b * factor) - b
            if extra < 0:
                raise ValueError("build_plus_scenario needs a factor of at least 1")
            days = list(calendar.month_days(m))
            extra_cells += [(dept, t, d, n) for t, d, n in allocate_to_cells(extra, history, dept, m, days)]
    return _add_extras(base, extra_cells, _EXTRA_STREAM_KEYS["plus20"], name, history)


def build_minus_scenario(base: Workload, factor: Fraction, name: str, *, calendar: Calendar) -> Workload:
    """-20% scenario: remove requests from the base workload, never add.

    For each department-month, the removal count is base total minus
    round_half_up(base total x factor). It is spread across that month's
    type-day cells in proportion to their base counts (largest remainder;
    cells ordered by type ID then day for ties). A cell never loses more than
    it holds. Within a cell, the requests generated last are removed.
    Every kept request keeps all its attributes.
    """
    req = base.requests
    month = calendar.month_of_day[req["arrival_day"].to_numpy()]
    req = req.assign(month=month)
    drop_seqs: list[np.ndarray] = []
    for (dept, m), g in req.groupby(["department", "month"], sort=False):
        b = len(g)
        remove = b - round_half_up(b * factor)
        if remove <= 0:
            continue
        cells = g.groupby(["type_id", "arrival_day"])["seq"].apply(lambda s: np.sort(s.to_numpy()))
        cells = cells.sort_index()  # (type_id, day) order sets the tie-break
        per_cell = largest_remainder(remove, [len(s) for s in cells])
        for seqs, k in zip(cells, per_cell):
            if k > len(seqs):  # mathematically impossible, but guard anyway
                raise AssertionError("removal exceeded a cell's size")
            if k:
                drop_seqs.append(seqs[-k:])  # the last-generated requests of the cell
    dropped = np.concatenate(drop_seqs) if drop_seqs else np.array([], dtype=np.int64)
    kept = base.requests[~base.requests["seq"].isin(dropped)].reset_index(drop=True)
    return Workload(name, kept, base.window_sources, list(base.warnings))


def build_spike_scenario(base: Workload, name: str, *, history: History, calendar: Calendar) -> Workload:
    """Snowstorm: triple Public Works arrivals on February 10-12, 2025.

    Every base request is kept. For each Public Works type-day cell on a
    spike day, (multiplier - 1) x the cell's base count extra requests of the
    same type are added on that day, so the cell ends at exactly 3x its base
    count. Extras draw attributes from the spike sub-stream.
    """
    spike_days = {calendar.day_index(d) for d in config.SPIKE_DATES}
    req = base.requests
    sel = req[(req["department"] == config.SPIKE_DEPT) & req["arrival_day"].isin(spike_days)]
    counts = sel.groupby(["type_id", "arrival_day"]).size()
    extra_cells = [
        (config.SPIKE_DEPT, tid, int(day), int(n) * (config.SPIKE_MULTIPLIER - 1)) for (tid, day), n in counts.items()
    ]
    return _add_extras(base, extra_cells, _EXTRA_STREAM_KEYS["spike"], name, history)


def build_all_workloads(forecast: pd.DataFrame, *, history: History | None = None) -> dict[str, Workload]:
    """Build the planning workload and all four evaluation workloads.

    Returns a dict with keys "planning", "base", "plus20", "minus20", "spike".
    Only "planning" may be given to the planner; the others are for scoring.
    """
    history = history or History.load()
    calendar = build_calendar()
    planning = build_base_workload(forecast, config.PLANNING_SEED, "planning", history=history, calendar=calendar)
    base = build_base_workload(forecast, config.EVALUATION_SEED, "base", history=history, calendar=calendar)
    return {
        "planning": planning,
        "base": base,
        "plus20": build_plus_scenario(base, config.SCENARIO_FACTORS["plus20"], "plus20", history=history, calendar=calendar),
        "minus20": build_minus_scenario(base, config.SCENARIO_FACTORS["minus20"], "minus20", calendar=calendar),
        "spike": build_spike_scenario(base, "spike", history=history, calendar=calendar),
    }
