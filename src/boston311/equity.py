"""Neighborhood equity in historical response times (deliverable 6).

[Added module; see spec section 11.3.] This answers one question with
2023-2024 data: did residents in some neighborhoods get less on-time service
than others *for the same kinds of requests*?

Why a "mix-adjusted" comparison is needed
-----------------------------------------
Some neighborhoods mostly file request types that are hard to close on time,
and others mostly file easy ones. Comparing raw on-time rates would blame a
neighborhood for its request mix. So for each neighborhood we also compute
the on-time rate it would be *expected* to have if each of its requests had
been served at that type's citywide on-time rate (within the same
department). This is called indirect standardization:

    expected rate = sum over types of (requests of that type x citywide rate of that type)
                    / all requests

    gap = actual rate - expected rate

A neighborhood well below its own expectation (a negative gap) is a real
signal worth investigating; a low raw rate with a zero gap is just its mix.

Limits (stated in the notebook): this is descriptive, not causal. Differences
can come from how requests are reported (app vs. phone, employee vs.
resident) as well as from how they are served, and there is no population
data, so nothing here is per resident. On-time uses the city's own flag over
requests with a target date.
"""

from __future__ import annotations

import pandas as pd

from boston311 import config
from boston311.data import load_processed

# Neighborhood-department groups with fewer requests (with a target date) than
# this are shown but flagged as too small to compare reliably.
MIN_EQUITY_SAMPLE = 100


def neighborhood_equity() -> pd.DataFrame:
    """One row per department x neighborhood with actual, expected, and gap.

    Columns: department, neighborhood, requests, with_target, on_time_rate,
    expected_on_time_rate, gap_pct_points, median_days_to_close,
    small_sample.
    """
    nts = load_processed("neighborhood_type_stats")
    ns = load_processed("neighborhood_stats")

    # Citywide on-time rate of each type within its department.
    city = nts.groupby(["department", "type_id"])[["with_target", "on_time"]].sum()
    city_rate = (city["on_time"] / city["with_target"]).rename("city_rate")

    # Expected on-time requests per neighborhood, given its own type mix.
    t = nts.join(city_rate, on=["department", "type_id"])
    t = t[t["with_target"] > 0]
    t["expected_on_time"] = t["with_target"] * t["city_rate"]
    expected = t.groupby(["department", "neighborhood"])["expected_on_time"].sum()

    out = ns.set_index(["department", "neighborhood"]).join(expected).reset_index()
    out["on_time_rate"] = out["on_time"] / out["with_target"]
    out["expected_on_time_rate"] = out["expected_on_time"] / out["with_target"]
    out["gap_pct_points"] = 100 * (out["on_time_rate"] - out["expected_on_time_rate"])
    out["small_sample"] = out["with_target"] < MIN_EQUITY_SAMPLE
    cols = [
        "department",
        "neighborhood",
        "requests",
        "with_target",
        "on_time_rate",
        "expected_on_time_rate",
        "gap_pct_points",
        "median_days_to_close",
        "small_sample",
    ]
    order = {d: i for i, d in enumerate(config.DEPT_CODES)}
    return (
        out[cols]
        .sort_values(["department", "gap_pct_points"], key=lambda s: s.map(order) if s.name == "department" else s)
        .reset_index(drop=True)
        .round({"on_time_rate": 3, "expected_on_time_rate": 3, "gap_pct_points": 1})
    )


def equity_summary(table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per department: the spread of raw rates and of mix-adjusted gaps.

    Only neighborhoods with a reliable sample (and a known neighborhood) are
    included, so one tiny group cannot set the range.
    """
    table = neighborhood_equity() if table is None else table
    ok = table[~table["small_sample"] & (table["neighborhood"] != config.UNSPECIFIED_NEIGHBORHOOD)]
    rows = []
    for dept in config.DEPT_CODES:
        d = ok[ok["department"] == dept]
        worst, best = d.loc[d["gap_pct_points"].idxmin()], d.loc[d["gap_pct_points"].idxmax()]
        rows.append(
            {
                "department": dept,
                "neighborhoods": len(d),
                "raw_on_time_min": d["on_time_rate"].min(),
                "raw_on_time_max": d["on_time_rate"].max(),
                "largest_negative_gap": f"{worst['neighborhood']} ({worst['gap_pct_points']:+.1f} pts)",
                "largest_positive_gap": f"{best['neighborhood']} ({best['gap_pct_points']:+.1f} pts)",
            }
        )
    return pd.DataFrame(rows)
