"""Tests for the calendar and the daily FIFO simulator (spec 4.3).

Hand-calculated examples from spec section 8: E8, E9, E10 (simulator part),
E12. A naive reference simulator, written as directly as possible from the
spec's "daily order of events", cross-checks the fast simulator on a full
year of real-sized data.
"""

from __future__ import annotations

from collections import deque
from datetime import date

import numpy as np
import pytest

from boston311 import config
from boston311.simulate import NEVER, Requests, build_calendar, daily_capacity_from_crews, period_stats, simulate


def capacity_on(days: dict[int, int], n_days: int = 400) -> np.ndarray:
    """A capacity array that is zero except on the given {day: capacity}."""
    cap = np.zeros(n_days, dtype=np.int64)
    for d, c in days.items():
        cap[d] = c
    return cap


# ---------------------------------------------------------------------------
# E12. Calendar
# ---------------------------------------------------------------------------


def test_e12_february_adds_first_saturday(calendar):
    feb = [d for d in calendar.month_days(2) if calendar.service[d]]
    weekdays = [d for d in calendar.month_days(2) if calendar.dates[d].weekday() < 5]
    assert len(weekdays) == 20
    assert len(feb) == 21
    # The 21 service days are the 20 weekdays plus Saturday, February 1.
    assert set(feb) == set(weekdays) | {calendar.day_index("2025-02-01")}


def test_e12_month_with_23_weekdays_uses_first_21(calendar):
    jan_weekdays = [d for d in calendar.month_days(1) if calendar.dates[d].weekday() < 5]
    assert len(jan_weekdays) == 23
    service = [d for d in calendar.month_days(1) if calendar.service[d]]
    assert service == jan_weekdays[:21]
    # January 30 and 31 (the 22nd and 23rd weekdays) are not service days.
    assert not calendar.service[calendar.day_index("2025-01-30")]
    assert not calendar.service[calendar.day_index("2025-01-31")]


def test_every_month_has_21_service_days(calendar):
    assert [calendar.service_days_in_month(m) for m in range(1, 13)] == [21] * 12
    assert calendar.dates[0] == date(2025, 1, 1) and calendar.n_days == 365


# ---------------------------------------------------------------------------
# E8. Deadline boundaries (target day 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "close_on, expected_cost",
    [(5, 0), (6, 20), (35, 20), (None, 120)],  # None = still open at end of day 35
)
def test_e8_deadline_boundaries(close_on, expected_cost):
    req = Requests.from_lists(arrival_day=[0], target_day=[5])
    cap = capacity_on({} if close_on is None else {close_on: 1})
    result = simulate(req, 0, 0, 40, cap)
    stats = period_stats(result, 0, 40)
    assert stats.penalty_cost == expected_cost


# ---------------------------------------------------------------------------
# E9. FIFO with capacity
# ---------------------------------------------------------------------------


def test_e9_fifo_with_capacity():
    # One crew with capacity 2 per day. Day 1 arrivals in order: A (target 1),
    # B (target 2), C (target 1). Days 1 and 2 are service days.
    req = Requests.from_lists(arrival_day=[1, 1, 1], target_day=[1, 2, 1], seq=[0, 1, 2])
    result = simulate(req, 0, 0, 2, capacity_on({1: 2, 2: 2}, 3))
    # Day 1: A and B close. Day 2: C closes.
    assert result.close_day.tolist() == [1, 1, 2]
    day1 = period_stats(result, 1, 1)
    assert day1.closed_on_time == 2 and day1.overdue_events == 1  # C overdue at end of day 1
    day2 = period_stats(result, 2, 2)
    assert day2.late_completions == 1
    total = period_stats(result, 0, 2)
    assert (total.closed_on_time, total.overdue_events, total.penalty_cost) == (2, 1, 20)


# ---------------------------------------------------------------------------
# E10. Target classes in the simulator
# ---------------------------------------------------------------------------


def test_e10_no_target_request_consumes_capacity_without_penalty():
    # A no-target request arrives first, then a valid one due the same day.
    # With capacity 1, the no-target request takes the only slot.
    req = Requests.from_lists(arrival_day=[0, 0], target_day=[None, 0])
    result = simulate(req, 0, 0, 1, capacity_on({0: 1, 1: 1}, 2))
    stats = period_stats(result, 0, 1)
    assert stats.no_target_closed == 1
    assert stats.overdue_events == 1  # only the valid request is penalised
    assert result.close_day.tolist() == [0, 1]


def test_e10_long_window_never_overdue_in_2025(calendar):
    req = Requests.from_lists(arrival_day=[10], target_day=[410])  # 400-day window
    result = simulate(req, 0, 0, calendar.n_days - 1, np.zeros(calendar.n_days, dtype=np.int64))
    stats = period_stats(result, 0, calendar.n_days - 1)
    assert stats.penalty_events == 0
    assert stats.open_not_yet_due_end == 1


# ---------------------------------------------------------------------------
# Simulator mechanics
# ---------------------------------------------------------------------------


def test_head_state_continues_across_calls():
    """Simulating two halves in sequence equals simulating the whole period."""
    rng = np.random.default_rng(0)
    arrivals = np.sort(rng.integers(0, 60, 500))
    targets = arrivals + rng.integers(0, 10, 500)
    req = Requests.from_lists(arrival_day=arrivals.tolist(), target_day=targets.tolist())
    cap = np.where(np.arange(70) % 7 < 5, 7, 0)
    whole = simulate(req, 0, 0, 59, cap)
    first = simulate(req, 0, 0, 29, cap)
    second = simulate(req, first.head_end, 30, 59, cap)
    assert second.head_end == whole.head_end
    # Requests closed in the second half have the same close day both ways.
    offset = first.head_end
    np.testing.assert_array_equal(second.close_day, whole.close_day[offset:])


def test_rejects_unsorted_requests():
    with pytest.raises(ValueError):
        Requests(np.array([2, 1]), np.array([True, True]), np.array([3, 3]), np.array([0, 1]))


def test_negative_crews_rejected(calendar):
    with pytest.raises(ValueError, match="cannot be negative"):
        daily_capacity_from_crews(calendar, {1: -1}, 4)


def naive_simulate(arrival_day, has_target, target_day, daily_capacity, n_days):
    """Reference simulator: a literal transcription of spec 4.3's daily order.

    Slow but obviously correct: a real queue (deque), one day at a time.
    Returns (close_day per request, overdue events per day, long events per day).
    """
    order = sorted(range(len(arrival_day)), key=lambda i: (arrival_day[i], i))
    by_day: dict[int, list[int]] = {}
    for i in order:
        by_day.setdefault(arrival_day[i], []).append(i)
    queue: deque[int] = deque()
    close = [NEVER] * len(arrival_day)
    is_open = [False] * len(arrival_day)
    overdue = np.zeros(n_days, dtype=int)
    long_overdue = np.zeros(n_days, dtype=int)
    for d in range(n_days):
        for i in by_day.get(d, []):  # 1. arrivals join the back
            queue.append(i)
            is_open[i] = True
        for _ in range(int(daily_capacity[d])):  # 2. close from the front
            if not queue:
                break
            i = queue.popleft()
            close[i] = d
            is_open[i] = False
        for i in queue:  # 3-4. end-of-day penalty checks on open requests
            if has_target[i] and target_day[i] == d:
                overdue[d] += 1
            if has_target[i] and target_day[i] + config.LONG_OVERDUE_DAYS == d:
                long_overdue[d] += 1
    return np.array(close), overdue, long_overdue


def test_fast_simulator_matches_naive_reference_on_real_workload(workloads, frozen_plan, calendar):
    """Cross-check on a full year of Inspectional Services (about 18,600 requests)."""
    dept = "ISD"
    req = workloads["base"].for_department(dept)
    dp = frozen_plan.departments[dept]
    crews = dp.regular_crews()
    cap = daily_capacity_from_crews(
        calendar, {m: crews[m] + dp.decision(m).seasonal_crews for m in range(1, 13)},
        config.DEPARTMENTS[dept].capacity_per_crew_day,
    )
    fast = simulate(req, 0, 0, calendar.n_days - 1, cap)
    close, overdue, long_overdue = naive_simulate(
        req.arrival_day.tolist(), req.has_target.tolist(), req.target_day.tolist(), cap, calendar.n_days
    )
    np.testing.assert_array_equal(fast.close_day, close)
    for m in range(1, 13):
        first, last = calendar.month_first_day[m], calendar.month_last_day[m]
        st = period_stats(fast, first, last)
        assert st.overdue_events == overdue[first : last + 1].sum()
        assert st.long_overdue_events == long_overdue[first : last + 1].sum()
