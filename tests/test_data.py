"""Tests for the data pipeline and forecast (spec 4.1, 4.2, checks 5 and 7)."""

from __future__ import annotations

import pandas as pd
import pytest

from boston311 import config, data, forecast


def test_missing_column_error_names_the_column(tmp_path):
    cols = [c for c in config.REQUIRED_COLUMNS if c != "sla_target_dt"]
    path = tmp_path / "bad.csv"
    pd.DataFrame(columns=cols).to_csv(path, index=False)
    with pytest.raises(data.MissingColumnError, match="sla_target_dt"):
        data.check_columns(path)


def test_target_classes_and_windows():
    raw = pd.DataFrame(
        {
            "case_enquiry_id": ["1", "2", "3", "3"],  # "3" is a duplicate
            "open_dt": ["2024-01-05 23:59:00", "2024-01-05 08:00:00", "2024-01-05 08:00:00", "2024-01-05 08:00:00"],
            "sla_target_dt": ["2024-01-06 00:01:00", None, "2024-01-04 09:00:00", "2024-01-04 09:00:00"],
            "closed_dt": [None, None, None, None],
            "type": ["A"] * 4,
            "queue": ["Q"] * 4,
            "department": ["ISD"] * 4,
            "case_title": ["Fish &amp; Chips", None, None, None],
            "neighborhood": [None] * 4,
            "source": ["x"] * 4,
            "on_time": ["ONTIME"] * 4,
        }
    )
    clean, counts = data.clean_requests(raw)
    assert counts["duplicates_removed"] == 1
    assert clean["target_class"].tolist() == ["valid", "missing", "invalid_ordering"]
    # Calendar-date difference: 23:59 on Jan 5 to 00:01 on Jan 6 is a 1-day window.
    assert clean["window_days"].iloc[0] == 1
    assert clean["case_title"].iloc[0] == "Fish & Chips"  # HTML entity decoded


def test_2024_counts_reconcile_with_project_page():
    report = data.load_reconciliation()
    for code, check in report["page_check_2024"].items():
        assert check["match"], f"{code}: ours {check['ours']} vs page {check['page']}"


def test_forecast_is_seasonal_naive_from_2024():
    md = data.load_processed("monthly_demand")
    f = forecast.forecast_2025(md)
    assert len(f) == 48
    for dept in config.DEPT_CODES:
        assert f[f["department"] == dept]["forecast"].sum() == config.DEPARTMENTS[dept].requests_2024


def test_forecast_never_reads_past_2024():
    md = data.load_processed("monthly_demand")
    leaked = pd.concat([md, pd.DataFrame([{"department": "ISD", "year": 2025, "month": 1, "requests": 5}])])
    with pytest.raises(ValueError, match="training cutoff"):
        forecast.forecast_2025(leaked)


def test_backtest_reports_every_department():
    bt = forecast.backtest()
    assert bt["department"].tolist() == list(config.DEPT_CODES)
    assert (bt["mape_pct"] > 0).all()
