"""2025 monthly demand forecast per department (spec section 4.2).

The method is a **seasonal naive** forecast: each 2025 month is predicted to
have exactly as many requests as the same month of 2024. For example, the
forecast for Public Works in August 2025 is the Public Works count of
August 2024.

Why so simple? Demand here is strongly seasonal (Parks more than triples
from January to June) and we only have two years of history. With two years,
a fancier model cannot be validated fairly, and the spec says the baseline is
final unless a candidate model can be. We still report how well the same
method would have done one year earlier (predicting 2024 from 2023), so the
reader knows how much to trust it.

Only data up to December 2024 is used (spec check 5).
"""

from __future__ import annotations

import pandas as pd

from boston311 import config
from boston311.data import load_processed


def seasonal_naive(monthly_demand: pd.DataFrame, *, source_year: int, target_year: int) -> pd.DataFrame:
    """Predict every month of ``target_year`` as the same month of ``source_year``.

    Args:
        monthly_demand: table with columns department, year, month, requests.
        source_year: the year whose months are copied.
        target_year: the year being predicted.

    Returns:
        A table with columns department, month, forecast (an integer), one
        row per department and month, in the fixed department order.
    """
    if source_year >= target_year:
        raise ValueError("source_year must be before target_year")
    src = monthly_demand[monthly_demand["year"] == source_year]
    rows = []
    for dept in config.DEPT_CODES:
        for month in range(1, 13):
            match = src[(src["department"] == dept) & (src["month"] == month)]
            # Every department has requests in every month of 2023 and 2024;
            # if a month were missing we would rather fail loudly than invent 0.
            if len(match) != 1:
                raise ValueError(f"No {source_year} demand for {dept} month {month}")
            rows.append({"department": dept, "month": month, "forecast": int(match["requests"].iloc[0])})
    return pd.DataFrame(rows)


def forecast_2025(monthly_demand: pd.DataFrame | None = None) -> pd.DataFrame:
    """The official 2025 forecast: 2025 month m = 2024 month m."""
    if monthly_demand is None:
        monthly_demand = load_processed("monthly_demand")
    # Guard for spec check 5: the forecast must never read past December 2024.
    if monthly_demand["year"].max() > 2024:
        raise ValueError("Forecast input contains data after the December 2024 training cutoff")
    return seasonal_naive(monthly_demand, source_year=2024, target_year=config.PLAN_YEAR)


def backtest(monthly_demand: pd.DataFrame | None = None) -> pd.DataFrame:
    """Score the same method one year earlier: predict 2024 from 2023.

    Returns one row per department with the annual totals and two error
    measures over the 12 months:

    * MAPE (mean absolute percentage error): the average of
      |forecast - actual| / actual, as a percentage.
    * Annual bias: (forecast total - actual total) / actual total, as a
      percentage. Negative means the method under-predicted.
    """
    if monthly_demand is None:
        monthly_demand = load_processed("monthly_demand")
    pred = seasonal_naive(monthly_demand, source_year=2023, target_year=2024)
    actual = monthly_demand[monthly_demand["year"] == 2024][["department", "month", "requests"]]
    merged = pred.merge(actual, on=["department", "month"])
    merged["ape"] = (merged["forecast"] - merged["requests"]).abs() / merged["requests"]
    out = merged.groupby("department", sort=False).agg(
        forecast_total=("forecast", "sum"), actual_total=("requests", "sum"), mape=("ape", "mean")
    )
    out["mape_pct"] = (out.pop("mape") * 100).round(1)
    out["annual_bias_pct"] = ((out["forecast_total"] / out["actual_total"] - 1) * 100).round(1)
    return out.reindex(list(config.DEPT_CODES)).reset_index()
