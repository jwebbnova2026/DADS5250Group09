"""Tests for workload generation and scenario coupling (spec 4.3).

Hand-calculated examples from spec section 8: E10 (generation part), E11,
E14, E17.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from boston311 import config
from boston311.workload import (
    History,
    WindowSampler,
    _draw_attributes,
    build_base_workload,
    largest_remainder,
    round_half_up,
)

# ---------------------------------------------------------------------------
# Exact rounding
# ---------------------------------------------------------------------------


def test_largest_remainder_spec_example():
    # E17's unit test: recomputing for a bigger total can shrink a cell.
    assert largest_remainder(5, [1, 3, 7]) == [1, 1, 3]
    assert largest_remainder(6, [1, 3, 7]) == [0, 2, 4]


def test_largest_remainder_ties_go_to_earlier_item():
    assert largest_remainder(1, [1, 1, 1]) == [1, 0, 0]
    assert largest_remainder(2, [1, 1, 1]) == [1, 1, 0]


@pytest.mark.parametrize("total", [0, 1, 17, 1000, 12345])
def test_largest_remainder_preserves_total(total):
    assert sum(largest_remainder(total, [5, 0, 13, 2, 7])) == total


def test_round_half_up():
    assert round_half_up(Fraction(5, 2)) == 3  # Python's round(2.5) would give 2
    assert round_half_up(Fraction(1557) * Fraction(4, 5)) == 1246
    assert round_half_up(Fraction(7, 3)) == 2


# ---------------------------------------------------------------------------
# E11. Window fallback chain
# ---------------------------------------------------------------------------


def test_e11_fallback_to_department():
    windows = pd.DataFrame(
        {
            "department": ["ISD", "ISD"],
            "type_id": ["T_small", "T_big"],
            "window_days": [3, 30],
            "requests": [12, 3000],  # 12 valid windows for the small type
        }
    )
    sampler = WindowSampler(windows)
    assert sampler.source_for("ISD", "T_small")[0] == "department"
    assert sampler.source_for("ISD", "T_big")[0] == "type"


def test_fallback_to_pooled_when_department_is_small():
    windows = pd.DataFrame(
        {"department": ["PARK", "ISD"], "type_id": ["A", "B"], "window_days": [1, 2], "requests": [10, 100]}
    )
    assert WindowSampler(windows).source_for("PARK", "A")[0] == "pooled"


# ---------------------------------------------------------------------------
# E10. Target classes in generation
# ---------------------------------------------------------------------------


def test_e10_no_target_classes_never_get_deadlines():
    history = History(
        type_month_2024=pd.DataFrame(),
        class_counts=pd.DataFrame(
            {"department": ["ISD", "ISD"], "type_id": ["A", "B"], "valid": [0, 0], "missing": [5, 0], "invalid_ordering": [0, 5]}
        ),
        windows=pd.DataFrame({"department": ["ISD"], "type_id": ["X"], "window_days": [3], "requests": [100]}),
    )
    cells = pd.DataFrame({"seq": range(4), "department": "ISD", "type_id": ["A", "A", "B", "B"], "arrival_day": 0})
    out = _draw_attributes(cells, np.random.default_rng(1), history, WindowSampler(history.windows))
    assert out["target_class"].tolist() == ["missing", "missing", "invalid_ordering", "invalid_ordering"]
    assert (out["target_day"] == -1).all() and (out["window_days"] == -1).all()


def test_generated_class_shares_track_history(workloads):
    """Each type's requests get classes at that type's historical shares.

    Expected missing share = sum over types of (requests generated for the
    type x the type's historical missing share) / all requests. The draw is
    random, so we allow a small tolerance (about 8 standard errors).
    """
    cc = History.load().class_counts.set_index(["department", "type_id"])
    p_missing = cc["missing"] / cc[["valid", "missing", "invalid_ordering"]].sum(axis=1)
    req = workloads["base"].requests
    n_by_type = req.groupby(["department", "type_id"]).size()
    expected = (n_by_type * p_missing.reindex(n_by_type.index)).sum() / len(req)
    got = (req["target_class"] == "missing").mean()
    assert abs(got - expected) < 0.005


# ---------------------------------------------------------------------------
# Arrivals
# ---------------------------------------------------------------------------


def test_arrivals_match_forecast_exactly(workloads, forecast_2025, calendar):
    for name in ("planning", "base"):
        got = workloads[name].monthly_totals(calendar).set_index(["department", "month"])["requests"]
        want = forecast_2025.set_index(["department", "month"])["forecast"]
        pd.testing.assert_series_equal(got.sort_index(), want.sort_index(), check_names=False)


def test_planning_and_base_have_identical_arrival_counts(workloads):
    key = ["department", "type_id", "arrival_day"]
    a = workloads["planning"].requests.groupby(key).size()
    b = workloads["base"].requests.groupby(key).size()
    pd.testing.assert_series_equal(a, b)


# ---------------------------------------------------------------------------
# E14. Stream separation and reproducibility
# ---------------------------------------------------------------------------


def test_e14_rebuilding_reproduces_each_stream(workloads, forecast_2025):
    again_plan = build_base_workload(forecast_2025, config.PLANNING_SEED, "planning")
    again_base = build_base_workload(forecast_2025, config.EVALUATION_SEED, "base")
    pd.testing.assert_frame_equal(again_plan.requests, workloads["planning"].requests)
    pd.testing.assert_frame_equal(again_base.requests, workloads["base"].requests)


# ---------------------------------------------------------------------------
# E17. Scenario coupling
# ---------------------------------------------------------------------------

ATTRS = ["seq", "department", "type_id", "arrival_day", "target_class", "window_days", "target_day"]


def _by_seq(w):
    return w.requests[ATTRS].set_index("seq").sort_index()


def test_e17_minus_is_subset_with_identical_attributes(workloads):
    base, minus = _by_seq(workloads["base"]), _by_seq(workloads["minus20"])
    assert minus.index.isin(base.index).all()
    pd.testing.assert_frame_equal(minus, base.loc[minus.index])


@pytest.mark.parametrize("scenario", ["plus20", "spike"])
def test_e17_plus_and_spike_are_supersets_with_identical_attributes(workloads, scenario):
    base, other = _by_seq(workloads["base"]), _by_seq(workloads[scenario])
    assert base.index.isin(other.index).all()
    pd.testing.assert_frame_equal(other.loc[base.index], base)


@pytest.mark.parametrize("scenario, factor", [("plus20", Fraction(6, 5)), ("minus20", Fraction(4, 5))])
def test_e17_scenario_totals_are_exact(workloads, calendar, scenario, factor):
    base = workloads["base"].monthly_totals(calendar).set_index(["department", "month"])["requests"]
    got = workloads[scenario].monthly_totals(calendar).set_index(["department", "month"])["requests"]
    for key, b in base.items():
        assert got[key] == round_half_up(b * factor), key


def test_e17_spike_triples_public_works_on_spike_days_only(workloads, calendar):
    spike_days = {calendar.day_index(d) for d in config.SPIKE_DATES}
    key = ["department", "type_id", "arrival_day"]
    base = workloads["base"].requests.groupby(key).size()
    spike = workloads["spike"].requests.groupby(key).size()
    for (dept, tid, day), n in base.items():
        expected = n * 3 if dept == "PWDx" and day in spike_days else n
        assert spike[(dept, tid, day)] == expected
    assert spike.sum() - base.sum() == 2 * base[[k for k in base.index if k[0] == "PWDx" and k[2] in spike_days]].sum()


def test_e17_cell_monotonicity(workloads):
    key = ["department", "type_id", "arrival_day"]
    base = workloads["base"].requests.groupby(key).size()
    for name, should_grow in (("plus20", True), ("spike", True), ("minus20", False)):
        other = workloads[name].requests.groupby(key).size().reindex(base.index.union(
            workloads[name].requests.groupby(key).size().index), fill_value=0)
        b = base.reindex(other.index, fill_value=0)
        assert ((other >= b) if should_grow else (other <= b)).all(), name
