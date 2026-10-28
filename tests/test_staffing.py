"""Tests for the staffing heuristic, cost accounting, and reconciliation (spec 4.4).

Hand-calculated examples from spec section 8: E1-E7, E5b, E5c, E13, E15,
E16, plus the full-dataset reconciliation (check 8) on every plan and
scenario.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from boston311 import config, staffing, workload
from boston311.simulate import PeriodStats, Requests, build_calendar, simulate
from boston311.staffing import (
    DepartmentPlan,
    MonthDecision,
    MonthProjection,
    Projector,
    SeasonalCrewError,
    StaffingInputError,
    hires_from_shortages,
    release_passes,
    release_window_cost,
    score_department,
    year_end_report,
)


def plan_with(dept: str, **by_month: MonthDecision) -> DepartmentPlan:
    """A department plan with no decisions except the given months (m1=..., m6=...)."""
    decisions = [by_month.get(f"m{m}", MonthDecision(m)) for m in range(1, 13)]
    return DepartmentPlan(dept, decisions)


def tiny_requests() -> Requests:
    """One request per month (enough to exercise scoring without real data)."""
    cal = build_calendar()
    days = [cal.month_first_day[m] for m in range(1, 13)]
    return Requests.from_lists(arrival_day=days, target_day=[d + 400 for d in days])


def stats(events: int = 0, open_end: int = 0) -> PeriodStats:
    """PeriodStats with only the fields the release rule reads set."""
    return PeriodStats(0, 0, 0, 0, 0, events, 0, open_end, 0, 0, open_end, 0)


def mp(month: int, regular: int, seasonal: int = 0, events: int = 0, open_end: int = 0) -> MonthProjection:
    return MonthProjection(month, regular, seasonal, 0, stats(events, open_end), 0)


# ---------------------------------------------------------------------------
# E1. Hiring delay and paid training
# ---------------------------------------------------------------------------


def test_e1_hiring_delay_and_paid_training():
    dp = plan_with("ISD", m3=MonthDecision(3, hires_ordered=2))
    rows, _ = score_department(dp, tiny_requests(), "test", "base", build_calendar())
    march, april = rows[2], rows[3]
    assert march.regular_crews == 16 and march.capacity == 16 * 4 * 21 == 1344
    assert march.regular_cost == pytest.approx(18 * 140_000 / 12) == pytest.approx(210_000)  # trainees paid
    assert april.regular_crews == 18 and april.capacity == 1512 and april.hires_started == 2
    assert april.regular_cost == pytest.approx(210_000)


# ---------------------------------------------------------------------------
# E2, E3. Hiring persistence and horizon
# ---------------------------------------------------------------------------


def test_e2_hiring_persistence():
    assert hires_from_shortages("PWDx", 1, 3, 0)[0] == 0  # shortage in February only
    assert hires_from_shortages("PWDx", 1, 3, 2)[0] == 2  # hire the smaller shortage


def test_e3_no_hires_after_october():
    assert hires_from_shortages("PWDx", 11, 5, 5)[0] == 0
    assert hires_from_shortages("PWDx", 10, 5, 5)[0] == 5


def test_parks_never_starts_permanent_crew_in_season():
    for t in range(3, 10):  # first productive month t+1 is April..October
        hires, note = hires_from_shortages("PARK", t, 4, 4)
        assert hires == 0 and "blocked" in note
    assert hires_from_shortages("PARK", 2, 4, 4)[0] == 4  # productive March
    assert hires_from_shortages("PARK", 10, 4, 4)[0] == 4  # productive November


# ---------------------------------------------------------------------------
# E4. Release notice and severance
# ---------------------------------------------------------------------------


def test_e4_release_notice_and_severance():
    dp = plan_with("PWDx", m6=MonthDecision(6, releases_noticed=1))
    rows, _ = score_department(dp, tiny_requests(), "test", "base", build_calendar())
    june, july = rows[5], rows[6]
    assert june.regular_crews == 50  # the noticed crew still works in June
    assert june.severance_cost == pytest.approx(32_500)
    assert june.regular_cost == pytest.approx(50 * 130_000 / 12)  # includes its June salary of 10,833.33
    assert july.regular_crews == 49 and july.releases_effective == 1


# ---------------------------------------------------------------------------
# E5, E5b, E5c, E6. Release checks
# ---------------------------------------------------------------------------


def test_e5_release_blocked_by_more_events():
    keep = [mp(m, 10) for m in range(2, 6)]
    cut = [mp(m, 9, events=1 if m == 5 else 0) for m in range(2, 6)]
    assert not release_passes(keep, cut, keep_cost=100.0, cut_cost=50.0)


def test_e5b_release_blocked_by_cost():
    # Releasing one Parks crew in January: no added events, but one extra
    # seasonal crew in April and May.
    jan = mp(1, 10)
    keep = [mp(2, 10), mp(3, 10), mp(4, 10, seasonal=2), mp(5, 10, seasonal=2)]
    cut = [mp(2, 9), mp(3, 9), mp(4, 9, seasonal=3), mp(5, 9, seasonal=3)]
    keep_cost = release_window_cost("PARK", jan, keep, 0)
    cut_cost = release_window_cost("PARK", jan, cut, 1)
    assert cut_cost - keep_cost == pytest.approx(-40_000 + 26_000 + 30_000) == pytest.approx(16_000)
    assert not release_passes(keep, cut, keep_cost, cut_cost)


def test_e5c_release_blocked_by_end_of_horizon_backlog():
    keep = [mp(m, 10, open_end=100) for m in range(2, 6)]
    cut = [mp(m, 9, open_end=150) for m in range(2, 6)]  # no extra events, cheaper, but more backlog
    assert not release_passes(keep, cut, keep_cost=100.0, cut_cost=50.0)
    cut_ok = [mp(m, 9, open_end=100) for m in range(2, 6)]
    assert release_passes(keep, cut_ok, keep_cost=100.0, cut_cost=50.0)


def test_e6_no_release_after_august():
    cal = build_calendar()
    empty = Requests.from_lists(arrival_day=[0], target_day=[None])  # huge surplus
    proj = Projector("PWDx", empty, cal)
    assert staffing._release_decision(proj, 1, 9, 50, 0)[0] == 0
    assert staffing._release_decision(proj, 1, 8, 50, 0)[0] > 0  # same surplus in August does release


def test_release_with_real_cost_check_on_an_idle_department():
    """With no work at all, the release saves salary and passes every test."""
    cal = build_calendar()
    empty = Requests.from_lists(arrival_day=[0], target_day=[None])
    proj = Projector("ISD", empty, cal)
    k, note = staffing._release_decision(proj, 1, 1, 16, 0)
    # 5 months at 16 crews vs 1 month at 16 and 4 at 16-k, plus severance of
    # 3 months' salary per crew: saving 4 months - 3 months > 0 for every k.
    assert k == 16 - config.MIN_REGULAR_CREWS and "notice" in note


# ---------------------------------------------------------------------------
# E7. Parks seasonal eligibility
# ---------------------------------------------------------------------------


def test_e7_seasonal_in_march_is_rejected():
    with pytest.raises(SeasonalCrewError):
        plan_with("PARK", m3=MonthDecision(3, seasonal_crews=3))


def test_e7_seasonal_outside_parks_is_rejected():
    with pytest.raises(SeasonalCrewError):
        plan_with("PWDx", m5=MonthDecision(5, seasonal_crews=1))


def test_e7_seasonal_capacity_and_cost():
    dp = plan_with("PARK", m4=MonthDecision(4, seasonal_crews=3))
    rows, _ = score_department(dp, tiny_requests(), "test", "base", build_calendar())
    april, may = rows[3], rows[4]
    assert april.capacity - 10 * 6 * 21 == 3 * 6 * 21 == 378
    assert april.seasonal_cost == pytest.approx(3 * 1.3 * 10_000) == pytest.approx(39_000)
    assert may.seasonal_cost == 0 and may.severance_cost == 0  # nothing charged when they end


# ---------------------------------------------------------------------------
# Parks seasonal service floor (spec 4.4 step 2, decided 2026-10-23)
# ---------------------------------------------------------------------------


def april_requests(per_day: int, window: int, saturday_same_day: int = 0) -> Requests:
    """Parks-style requests arriving every day of April 2025.

    ``per_day`` requests a day with a ``window``-day target, plus optionally
    ``saturday_same_day`` requests each Saturday due the same day (Saturdays
    are not service days in April, so those can never be on time).
    """
    cal = build_calendar()
    arrivals, targets = [], []
    for d in cal.month_days(4):
        arrivals += [d] * per_day
        targets += [d + window] * per_day
        if cal.dates[d].weekday() == 5:
            arrivals += [d] * saturday_same_day
            targets += [d] * saturday_same_day
    order = sorted(range(len(arrivals)), key=lambda i: arrivals[i])
    return Requests.from_lists([arrivals[i] for i in order], [targets[i] for i in order])


def test_seasonal_floor_uses_fewest_crews_meeting_target():
    proj = Projector("PARK", april_requests(per_day=90, window=2), build_calendar())
    s = proj.seasonal_needed(0, 4, 10)
    assert s > 0  # 10 crews (60/service day) cannot keep up with 90 arrivals a day
    assert proj.month_on_time_rate(0, 4, 10 + s) >= config.SEASONAL_ON_TIME_TARGET
    assert proj.month_on_time_rate(0, 4, 10 + s - 1) < config.SEASONAL_ON_TIME_TARGET


def test_seasonal_floor_falls_back_to_best_possible_rate():
    # Many same-day Saturday requests: even unlimited capacity misses them,
    # so the best reachable rate is below 93% and the rule stops there.
    proj = Projector("PARK", april_requests(per_day=10, window=2, saturday_same_day=40), build_calendar())
    s = proj.seasonal_needed(0, 4, 10)
    best = proj.month_on_time_rate(0, 4, 10 + 1000)
    assert best < config.SEASONAL_ON_TIME_TARGET
    assert proj.month_on_time_rate(0, 4, 10 + s) == pytest.approx(best)
    if s > 0:
        assert proj.month_on_time_rate(0, 4, 10 + s - 1) < best


def test_seasonal_frontier_is_ordered_and_restores_config(workloads):
    df = staffing.seasonal_frontier(workloads, targets=(0.5, 0.93, 1.0))
    assert config.SEASONAL_ON_TIME_TARGET == 0.93  # the global setting is restored
    assert df["rule"].tolist() == ["baseline (January crews)", "floor 50%", "floor 93%", "every avoidable miss"]
    assert df["chosen"].tolist() == [False, False, True, False]
    # For widely spaced targets, a higher target buys more seasonal crew-months
    # and a higher on-time rate. (Between close targets the full re-plan can
    # wobble, because later hiring reacts to the seasonal choice.)
    floors = df.iloc[1:]
    assert floors["seasonal_crew_months"].is_monotonic_increasing
    assert floors["parks_on_time_rate"].is_monotonic_increasing


def test_seasonal_rule_only_for_parks_in_season():
    req = april_requests(per_day=200, window=1)
    cal = build_calendar()
    assert Projector("PWDx", req, cal).seasonal_needed(0, 4, 1) == 0
    assert Projector("PARK", req, cal).seasonal_needed(0, 3, 1) == 0  # March is out of season


# ---------------------------------------------------------------------------
# Terminal rules apply to EVERY plan, not only the heuristic's (R3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("month", [11, 12])
def test_hire_orders_after_october_are_rejected(month):
    with pytest.raises(StaffingInputError, match="hires_ordered"):
        plan_with("PWDx", **{f"m{month}": MonthDecision(month, hires_ordered=1)})


@pytest.mark.parametrize("month", [9, 10, 11, 12])
def test_release_notices_after_august_are_rejected(month):
    with pytest.raises(StaffingInputError, match="releases_noticed"):
        plan_with("PWDx", **{f"m{month}": MonthDecision(month, releases_noticed=1)})


def test_last_allowed_months_are_valid():
    dp = plan_with("PWDx", m10=MonthDecision(10, hires_ordered=1), m8=MonthDecision(8, releases_noticed=1))
    assert dp.regular_crews()[11] == 50  # 50 - 1 (left in September) + 1 (started in November)


def test_plan_cannot_be_edited_after_validation():
    dp = plan_with("PWDx")
    with pytest.raises(TypeError):  # decisions are an immutable tuple
        dp.decisions[10] = MonthDecision(11, hires_ordered=1)
    with pytest.raises(AttributeError):  # the plan object itself is frozen
        dp.decisions = tuple(MonthDecision(m, hires_ordered=1) for m in range(1, 13))


def test_scoring_revalidates_the_plan(calendar):
    """Defense in depth: scoring re-checks the plan even if validation was bypassed."""
    dp = plan_with("PWDx")
    bad = list(dp.decisions)
    bad[10] = MonthDecision(11, hires_ordered=1)
    object.__setattr__(dp, "decisions", tuple(bad))  # deliberately bypass the frozen dataclass
    with pytest.raises(StaffingInputError, match="hires_ordered"):
        score_department(dp, tiny_requests(), "test", "base", calendar)


def test_invalid_staffing_input_names_parameter():
    with pytest.raises(StaffingInputError, match="hires_ordered"):
        plan_with("ISD", m2=MonthDecision(2, hires_ordered=-1))
    with pytest.raises(StaffingInputError, match="releases_noticed"):
        plan_with("ISD", m1=MonthDecision(1, releases_noticed=16))  # would leave 0 crews


# ---------------------------------------------------------------------------
# E13. Year end
# ---------------------------------------------------------------------------


def test_e13_year_end():
    cal = build_calendar()
    dec20, jan10_2026 = cal.day_index("2025-12-20"), cal.day_index("2025-12-31") + 10
    arrive = cal.day_index("2025-12-15")
    req = Requests.from_lists(arrival_day=[arrive, arrive], target_day=[dec20, jan10_2026])  # X, Y
    result = simulate(req, 0, 0, cal.n_days - 1, np.zeros(cal.n_days, dtype=np.int64))
    ye = year_end_report(result, plan_with("ISD"), costs_accrued=20.0)
    assert ye.open_overdue_charged == 1  # X: its $20 is accrued
    assert ye.long_threshold_in_2026 == 1  # X: Jan 19, 2026 threshold disclosed, not charged
    assert ye.open_long_overdue_charged == 0
    assert ye.not_yet_due == 1  # Y
    assert dec20 + config.LONG_OVERDUE_DAYS == cal.day_index("2025-12-31") + 19  # January 19, 2026


# ---------------------------------------------------------------------------
# E15. Planner isolation
# ---------------------------------------------------------------------------


def test_e15_planner_takes_only_the_planning_workload():
    params = list(inspect.signature(staffing.make_plan).parameters)
    assert params == ["planning_workload"]


def test_e15_planner_rejects_an_evaluation_workload(workloads):
    with pytest.raises(ValueError, match="planner isolation"):
        staffing.make_plan(workloads["base"])


def test_e15_plan_unchanged_when_evaluation_stream_changes(forecast_2025, frozen_plan, monkeypatch):
    # Build ONLY a planning workload (no evaluation data exists at all), with
    # a different evaluation seed configured. The frozen plan must not change.
    monkeypatch.setattr(config, "EVALUATION_SEED", 999)
    planning = workload.build_base_workload(forecast_2025, config.PLANNING_SEED, "planning")
    again = staffing.make_plan(planning)
    assert again.to_frame().equals(frozen_plan.to_frame())


# ---------------------------------------------------------------------------
# E16. Long-deadline workload (Parks)
# ---------------------------------------------------------------------------


def test_e16_long_deadline_parks_work_carries_forward():
    cal = build_calendar()
    arrivals, targets = [], []
    for m in (4, 5, 6):  # 2,000 requests in each of April, May, June, all due in 2026
        days = list(cal.month_days(m))
        for i in range(2000):
            d = days[i % len(days)]
            arrivals.append(d)
            targets.append(400 + i % 30)
    req = Requests.from_lists(arrival_day=sorted(arrivals), target_day=targets)
    proj = Projector("PARK", req, cal)
    head = 0
    # Seasonal rule: nothing is due in 2025, so no on-time rate to protect: 0 crews.
    assert proj.seasonal_needed(head, 4, 10) == 0
    # Hiring rule sees the residual volume but the Parks restriction blocks it.
    hires, note = staffing._hire_decision(proj, head, 4, 10, 0)
    assert hires == 0 and "blocked" in note
    stats, _ = proj.run_month(head, 4, 10)
    assert stats.open_end == 2000 - 10 * 6 * 21  # work carries forward


# ---------------------------------------------------------------------------
# Checks 3 and 8: full-dataset reconciliation on every plan and scenario
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", config.SCENARIOS)
@pytest.mark.parametrize("plan_name", ["heuristic", "baseline"])
def test_full_reconciliation(workloads, frozen_plan, scenario, plan_name):
    plan = frozen_plan if plan_name == "heuristic" else staffing.baseline_plan()
    rows, year_ends = staffing.score_plan(plan, workloads[scenario], scenario)
    assert staffing.reconciliation_failures(rows, plan, workloads[scenario]) == []
    assert len(rows) == 48
    assert rows["total_cost"].sum() == pytest.approx(sum(ye.costs_accrued for ye in year_ends))
    # Terminal rules: nothing ordered or noticed in 2025 takes effect in 2026.
    assert all(ye.hires_ordered_effective_2026 == 0 and ye.notices_effective_2026 == 0 for ye in year_ends)


def test_frozen_plan_respects_terminal_rules(frozen_plan):
    df = frozen_plan.to_frame()
    assert (df.loc[df["month"] > config.LAST_HIRE_ORDER_MONTH, "hires_ordered"] == 0).all()
    assert (df.loc[df["month"] > config.LAST_RELEASE_NOTICE_MONTH, "releases_noticed"] == 0).all()
    # A month with a hire order never also has a release notice.
    assert not ((df["hires_ordered"] > 0) & (df["releases_noticed"] > 0)).any()
    park = df[df["department"] == "PARK"]
    assert (park.loc[~park["month"].isin(config.SEASONAL_MONTHS), "seasonal_crews"] == 0).all()
    # Parks: no permanent crew starts April-October.
    starts = park.set_index("month")["hires_ordered"].shift(1, fill_value=0)
    assert (starts[starts.index.isin(config.SEASONAL_MONTHS)] == 0).all()
