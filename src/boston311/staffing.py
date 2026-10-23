"""Staffing policy (the core heuristic), the fixed baseline, and cost accounting.

Spec section 5.4. Read this module in three parts:

1. **Plans.** A plan is, for each department and month, three numbers:
   hires ordered, release notices given, and Parks seasonal crews. Everything
   else (crews working, capacity, costs) follows from those numbers and the
   rules. :class:`DepartmentPlan` and :class:`Plan` hold them.

2. **Making the plan** (:func:`make_plan`). The planner walks through 2025
   month by month on the *planning workload only*, deciding at the start of
   each month, in this order:

   1. apply last month's decisions (new hires start, noticed crews leave);
   2. Parks only, April-October: choose seasonal crews;
   3. hire, if a shortage is projected in *both* of the next two months;
   4. Parks only: never start a permanent hire in April-October;
   5. release, only if no hire was ordered and a five-month projection shows
      no more penalty events, no higher cost, and no bigger backlog;
   6. simulate the month and move on.

   Every estimate comes from a *projection*: a copy of the planner's queue
   run forward through the simulator under a stated workforce. After
   December the decisions are frozen.

3. **Scoring a plan** (:func:`score_plan`). A frozen plan is replayed,
   unchanged, on any workload (base evaluation or a sensitivity scenario),
   producing one :class:`~boston311.schemas.StaffingRow` per department and
   month, plus a year-end report.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from boston311 import config
from boston311.schemas import StaffingRow
from boston311.simulate import (
    Calendar,
    PeriodStats,
    Requests,
    SimResult,
    build_calendar,
    daily_capacity_from_crews,
    open_at_start,
    period_stats,
    simulate,
)
from boston311.workload import Workload

# A capacity so large it can never run out; used for the "unlimited capacity"
# comparison in the seasonal rule.
UNLIMITED = 10**9

# ---------------------------------------------------------------------------
# Typed errors (spec section 6)
# ---------------------------------------------------------------------------


class StaffingInputError(ValueError):
    """Invalid staffing input. The message names the offending parameter."""

    def __init__(self, parameter: str, message: str):
        self.parameter = parameter
        super().__init__(f"{parameter}: {message}")


class SeasonalCrewError(StaffingInputError):
    """Seasonal crews requested outside Parks or outside April-October."""


def check_seasonal(dept: str, month: int, seasonal_crews: int) -> None:
    """Raise :class:`SeasonalCrewError` unless the seasonal request is allowed."""
    if seasonal_crews < 0:
        raise StaffingInputError("seasonal_crews", f"cannot be negative (got {seasonal_crews})")
    if seasonal_crews == 0:
        return
    if dept != config.SEASONAL_DEPT:
        raise SeasonalCrewError("seasonal_crews", f"only {config.SEASONAL_DEPT} may use seasonal crews, not {dept}")
    if month not in config.SEASONAL_MONTHS:
        raise SeasonalCrewError("seasonal_crews", f"seasonal crews are allowed April-October only, not month {month}")


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonthDecision:
    """The three decisions made at the start of one month."""

    month: int
    hires_ordered: int = 0
    releases_noticed: int = 0
    seasonal_crews: int = 0


@dataclass
class DepartmentPlan:
    """A department's 12 monthly decisions plus a human-readable log.

    ``log`` explains every non-trivial decision (for the report and for
    reviewers checking the heuristic by hand).
    """

    department: str
    decisions: list[MonthDecision]
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if [d.month for d in self.decisions] != list(range(1, 13)):
            raise StaffingInputError("decisions", "must contain exactly one decision per month, January to December")
        for d in self.decisions:
            if d.hires_ordered < 0:
                raise StaffingInputError("hires_ordered", f"cannot be negative (month {d.month})")
            if d.releases_noticed < 0:
                raise StaffingInputError("releases_noticed", f"cannot be negative (month {d.month})")
            check_seasonal(self.department, d.month, d.seasonal_crews)
        # The crew path must never go below the minimum.
        crews = self.regular_crews()
        if min(crews.values()) < config.MIN_REGULAR_CREWS:
            raise StaffingInputError("releases_noticed", f"would leave fewer than {config.MIN_REGULAR_CREWS} crew(s)")

    def decision(self, month: int) -> MonthDecision:
        return self.decisions[month - 1]

    def regular_crews(self) -> dict[int, int]:
        """Regular crews *working* each month.

        crews(1) = January crews (GIVEN); then
        crews(t) = crews(t-1) + hires ordered in t-1 - notices given in t-1.
        Trainees are not counted as working; noticed crews still work in
        their notice month.
        """
        crews = {1: config.DEPARTMENTS[self.department].start_crews}
        for t in range(2, 13):
            prev = self.decision(t - 1)
            crews[t] = crews[t - 1] + prev.hires_ordered - prev.releases_noticed
        return crews


@dataclass
class Plan:
    """A full plan: one :class:`DepartmentPlan` per department."""

    name: str
    departments: dict[str, DepartmentPlan]

    def to_frame(self) -> pd.DataFrame:
        """The plan as a table: department, month, decisions, and working crews."""
        rows = []
        for dept in config.DEPT_CODES:
            dp = self.departments[dept]
            crews = dp.regular_crews()
            for d in dp.decisions:
                rows.append(
                    {
                        "department": dept,
                        "month": d.month,
                        "regular_crews": crews[d.month],
                        "hires_ordered": d.hires_ordered,
                        "releases_noticed": d.releases_noticed,
                        "seasonal_crews": d.seasonal_crews,
                    }
                )
        return pd.DataFrame(rows)


def baseline_plan() -> Plan:
    """The fixed-workforce baseline: January crews all year, nothing else."""
    return Plan(
        "baseline",
        {d: DepartmentPlan(d, [MonthDecision(m) for m in range(1, 13)]) for d in config.DEPT_CODES},
    )


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonthProjection:
    """One projected month: workforce used, queue at its start, and results."""

    month: int
    regular_crews: int
    seasonal_crews: int
    open_start: int
    stats: PeriodStats
    capacity: int

    def cost(self, dept: str) -> float:
        """Salaries + seasonal + penalties for this month (severance added by caller)."""
        d = config.DEPARTMENTS[dept]
        return (
            self.regular_crews * d.monthly_cost
            + self.seasonal_crews * config.SEASONAL_COST_MULTIPLIER * d.monthly_cost
            + self.stats.penalty_cost
        )


class Projector:
    """Runs month-by-month projections for one department on one workload.

    The queue state passed around is ``head``: how many of the department's
    requests (in FIFO order) are already closed. See simulate.py for why one
    integer is enough.
    """

    def __init__(self, dept: str, requests: Requests, calendar: Calendar):
        self.dept = dept
        self.requests = requests
        self.calendar = calendar
        self.cap = config.DEPARTMENTS[dept].capacity_per_crew_day

    def run_month(self, head: int, month: int, crews: int | None) -> tuple[PeriodStats, int]:
        """Simulate one month with ``crews`` working crews (None = unlimited).

        Returns (stats for the month, head at the end of the month).
        """
        first, last = self.calendar.month_first_day[month], self.calendar.month_last_day[month]
        per_crew = UNLIMITED if crews is None else crews * self.cap
        capacity = np.where(self.calendar.service, per_crew, 0)
        result = simulate(self.requests, head, first, last, capacity)
        return period_stats(result, first, last), result.head_end

    def month_on_time_rate(self, head: int, month: int, crews: int) -> float | None:
        """Projected on-time rate of the requests *due* in ``month``.

        "Due in the month" means a valid target day inside the month. A due
        request is on time if it closes on or before its target day. Requests
        already closed before the month started (positions below ``head``)
        closed before their target, so they count as on time; every overdue
        one shows up as an overdue event of the one-month projection.
        Returns None if nothing is due in the month.
        """
        first, last = self.calendar.month_first_day[month], self.calendar.month_last_day[month]
        req = self.requests
        due = int(np.count_nonzero(req.has_target & (req.target_day >= first) & (req.target_day <= last)))
        if due == 0:
            return None
        overdue = self.run_month(head, month, crews)[0].overdue_events
        return 1 - overdue / due

    def seasonal_needed(self, head: int, month: int, regular: int) -> int:
        """Spec 5.4 step 2 (service-floor rule, DECIDED 2026-10-23): Parks
        seasonal crews for month t.

        Use the fewest seasonal crews S such that the projected on-time rate
        of requests due in month t is at least ``config.SEASONAL_ON_TIME_TARGET``
        (93%, Parks' own 2024 on-time rate). In plain words: buy service up to
        last year's standard, as cheaply as possible, and no further.

        If even unlimited capacity cannot reach the target in a month (for
        example because some same-day targets arrive on non-service days),
        the target for that month becomes the best rate unlimited capacity
        can reach, i.e. remove every avoidable miss and stop there.

        More crews never lower the on-time rate (requests can only close
        earlier), so a binary search finds the smallest S. Upper bound: once
        daily capacity covers everything open at the start of the month plus
        all of the month's arrivals, every service day clears the whole queue,
        which is exactly what unlimited capacity does.
        """
        if self.dept != config.SEASONAL_DEPT or month not in config.SEASONAL_MONTHS:
            return 0
        first, last = self.calendar.month_first_day[month], self.calendar.month_last_day[month]
        workload_bound = open_at_start(self.requests, head, first) + (
            self.requests.arrived_through(last) - self.requests.arrived_through(first - 1)
        )
        upper = max(0, math.ceil(workload_bound / self.cap) - regular)
        best_possible = self.month_on_time_rate(head, month, regular + upper)
        if best_possible is None:  # nothing due this month: no seasonal crews
            return 0
        target = min(config.SEASONAL_ON_TIME_TARGET, best_possible)
        lo, hi = 0, upper
        while lo < hi:  # invariant: hi always meets the target
            mid = (lo + hi) // 2
            if self.month_on_time_rate(head, month, regular + mid) >= target:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def project(
        self, head: int, months: list[int], regular_by_month: dict[int, int], seasonal_fixed: dict[int, int] | None = None
    ) -> tuple[list[MonthProjection], int]:
        """Project consecutive ``months`` under a stated regular-crew path.

        Seasonal crews: if a month appears in ``seasonal_fixed`` that number
        is used (the planner passes the S_t it already chose for the current
        month); otherwise the seasonal rule is applied to the projected queue
        at the start of that month (spec 5.4 step 3, "the seasonal rule
        applied to future Parks in-season months").
        """
        seasonal_fixed = seasonal_fixed or {}
        out = []
        for m in months:
            n = regular_by_month[m]
            s = seasonal_fixed[m] if m in seasonal_fixed else self.seasonal_needed(head, m, n)
            first = self.calendar.month_first_day[m]
            open_start = open_at_start(self.requests, head, first)
            stats, head = self.run_month(head, m, n + s)
            capacity = (n + s) * self.cap * self.calendar.service_days_in_month(m)
            out.append(MonthProjection(m, n, s, open_start, stats, capacity))
        return out, head


# ---------------------------------------------------------------------------
# The heuristic planner (spec 5.4)
# ---------------------------------------------------------------------------


def shortage_crews(open_start: int, arrivals: int, capacity: int, crew_month_capacity: int) -> int:
    """Crews missing in a month: ceil(max(0, open + arrivals - capacity) / C)."""
    return math.ceil(max(0, open_start + arrivals - capacity) / crew_month_capacity)


def hires_from_shortages(dept: str, t: int, shortage_next: int, shortage_after: int) -> tuple[int, str]:
    """The pure hiring rule (spec 5.4 steps 3-4), given the two shortages.

    * No hire orders after the start of October (terminal rule).
    * Hire only if *both* productive months t+1 and t+2 are short by at least
      one crew ("two-month persistence"), and then hire the smaller shortage.
    * Parks never orders a permanent crew whose first productive month
      (t+1) is April-October.

    Returns (hires, explanation); the explanation is "" when nothing happened.
    """
    if t > config.LAST_HIRE_ORDER_MONTH:
        return 0, ""
    if shortage_next < 1 or shortage_after < 1:
        return 0, ""
    hires = min(shortage_next, shortage_after)
    note = f"month {t}: projected shortage {shortage_next} crews in month {t + 1} and {shortage_after} in month {t + 2}"
    if config.PARKS_BLOCK_IN_SEASON_PERMANENT_HIRES and dept == config.SEASONAL_DEPT and (t + 1) in config.SEASONAL_MONTHS:
        return 0, note + f"; hire of {hires} blocked (a Parks permanent crew would start in season)"
    return hires, note + f"; ordered {hires} hire(s), productive from month {t + 1}"


def _hire_decision(proj: Projector, head: int, t: int, n: int, s_t: int) -> tuple[int, str]:
    """Spec 5.4 steps 3-4: how many crews to hire at the start of month t.

    Projects months t, t+1, t+2 with today's workforce (no new hires or
    releases; seasonal rule applied to future Parks in-season months). For
    each productive month m in {t+1, t+2} it computes

        shortage_m = ceil( max(0, open at start of m + arrivals in m
                                  - capacity in m) / C )

    where capacity includes any projected seasonal crews and C is one crew's
    monthly capacity, then applies :func:`hires_from_shortages`.
    """
    if t > config.LAST_HIRE_ORDER_MONTH:
        return 0, ""
    c = config.DEPARTMENTS[proj.dept].capacity_per_crew_month
    months = [t, t + 1, t + 2]
    projected, _ = proj.project(head, months, {m: n for m in months}, {t: s_t})
    s1, s2 = (shortage_crews(p.open_start, p.stats.arrivals, p.capacity, c) for p in projected[1:])
    return hires_from_shortages(proj.dept, t, s1, s2)


def release_window_cost(dept: str, month_t: MonthProjection, later: list[MonthProjection], released: int) -> float:
    """Projected total cost over months t .. t+4 for the release check.

    = salaries and seasonal crews and penalties of every projected month
      + severance (25% of annual cost per released crew) in month t.
    """
    severance = released * config.SEVERANCE_FRACTION * config.DEPARTMENTS[dept].annual_cost
    return month_t.cost(dept) + severance + sum(p.cost(dept) for p in later)


def release_passes(
    keep: list[MonthProjection], cut: list[MonthProjection], keep_cost: float, cut_cost: float
) -> bool:
    """The three release tests (spec 5.4 step 5) for one candidate.

    ``keep`` and ``cut`` are the projections of months t+1 .. t+4 without and
    with the release. The candidate passes only if, compared with keeping
    the crews:

    1. penalty events (both kinds) over months t+1 .. t+4 are no higher;
    2. projected total cost over months t .. t+4 is no higher;
    3. requests open at the end of month t+4 are no higher.
    """
    no_more_events = sum(p.stats.penalty_events for p in cut) <= sum(p.stats.penalty_events for p in keep)
    no_more_cost = cut_cost <= keep_cost
    no_more_backlog = cut[-1].stats.open_end <= keep[-1].stats.open_end
    return no_more_events and no_more_cost and no_more_backlog


def _release_decision(proj: Projector, head: int, t: int, n: int, s_t: int) -> tuple[int, str]:
    """Spec 5.4 step 5: how many crews to give notice at the start of month t.

    Compares, over months t .. t+4, the no-release projection with a
    projection where ``k`` crews leave from month t+1, for every
    k = 1 .. n - MIN_REGULAR_CREWS. A k passes only if all three hold:

    1. penalty events (both kinds) in months t+1 .. t+4 are no higher;
    2. total cost in months t .. t+4 is no higher, counting severance in
       month t, salaries, seasonal crews, and penalties;
    3. requests open at the end of month t+4 are no higher.

    The largest passing k is chosen. Returns (notices, explanation).
    """
    if t > config.LAST_RELEASE_NOTICE_MONTH:
        return 0, ""
    later = list(range(t + 1, t + 1 + config.RELEASE_LOOKAHEAD_MONTHS))
    # Month t is identical in every candidate (noticed crews still work), so
    # simulate it once and branch from the queue at the end of month t.
    (month_t,), head_after_t = proj.project(head, [t], {t: n}, {t: s_t})
    keep, _ = proj.project(head_after_t, later, {m: n for m in later})
    keep_cost = release_window_cost(proj.dept, month_t, keep, 0)

    best, best_note = 0, ""
    for k in range(1, n - config.MIN_REGULAR_CREWS + 1):
        cut, _ = proj.project(head_after_t, later, {m: n - k for m in later})
        cut_cost = release_window_cost(proj.dept, month_t, cut, k)
        if release_passes(keep, cut, keep_cost, cut_cost):
            best = k
            best_note = (
                f"month {t}: notice to {k} crew(s); over months {t}-{t + 4} projected cost "
                f"{cut_cost:,.0f} vs {keep_cost:,.0f}, events {sum(p.stats.penalty_events for p in cut)} vs "
                f"{sum(p.stats.penalty_events for p in keep)}, open at end {cut[-1].stats.open_end} vs "
                f"{keep[-1].stats.open_end}"
            )
    return best, best_note


def plan_department(dept: str, requests: Requests, calendar: Calendar | None = None) -> DepartmentPlan:
    """Run the heuristic for one department on its planning requests."""
    calendar = calendar or build_calendar()
    proj = Projector(dept, requests, calendar)
    head = 0  # zero backlog on January 1 (GIVEN)
    n = config.DEPARTMENTS[dept].start_crews
    pending_hires = pending_releases = 0  # nothing pending on January 1 (DEFAULT)
    decisions, log = [], []
    for t in range(1, 13):
        # Step 1: last month's orders start, last month's notices leave.
        n = n + pending_hires - pending_releases
        # Step 2: Parks seasonal crews for this month.
        s_t = proj.seasonal_needed(head, t, n)
        if s_t:
            log.append(f"month {t}: {s_t} seasonal crew(s)")
        # Steps 3-4: hiring.
        hires, note = _hire_decision(proj, head, t, n, s_t)
        if note:
            log.append(note)
        # Step 5: release, only if no hire was ordered this month.
        releases = 0
        if hires == 0:
            releases, note = _release_decision(proj, head, t, n, s_t)
            if note:
                log.append(note)
        decisions.append(MonthDecision(t, hires, releases, s_t))
        # Step 6: advance the planning run through month t.
        _, head = proj.run_month(head, t, n + s_t)
        pending_hires, pending_releases = hires, releases
    return DepartmentPlan(dept, decisions, log)


def make_plan(planning_workload: Workload) -> Plan:
    """Make and freeze the heuristic plan from the planning workload only.

    This function's only data input is the planning workload: it is never
    given an evaluation workload or an evaluation queue (spec 5.4, E15).
    """
    if planning_workload.name != "planning":
        raise ValueError(
            f"make_plan must be given the planning workload, not {planning_workload.name!r} (planner isolation)"
        )
    calendar = build_calendar()
    return Plan(
        "heuristic",
        {d: plan_department(d, planning_workload.for_department(d), calendar) for d in config.DEPT_CODES},
    )


# ---------------------------------------------------------------------------
# Scoring a frozen plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class YearEnd:
    """What remains at the end of December 31, 2025 (spec 5.5), per department."""

    department: str
    costs_accrued: float
    open_overdue_charged: int  # open, past target; their $20 is already in costs
    open_long_overdue_charged: int  # open, 30+ days past target; $120 already in costs
    long_threshold_in_2026: int  # open, past target, 30-day mark falls in 2026: disclosed, not charged
    not_yet_due: int  # open, target in 2026: future exposure, not charged
    open_no_target: int
    hires_ordered_effective_2026: int  # outstanding commitments (expected 0)
    notices_effective_2026: int  # outstanding commitments (expected 0)
    due_in_2025: int  # valid-target requests whose target day falls in 2025
    on_time_rate: float  # share of those closed by their target day


def score_department(
    dept_plan: DepartmentPlan, requests: Requests, plan_name: str, scenario: str, calendar: Calendar
) -> tuple[list[StaffingRow], YearEnd]:
    """Replay one department's frozen decisions on a workload for all of 2025."""
    dept = config.DEPARTMENTS[dept_plan.department]
    crews = dept_plan.regular_crews()
    working = {m: crews[m] + dept_plan.decision(m).seasonal_crews for m in range(1, 13)}
    capacity = daily_capacity_from_crews(calendar, working, dept.capacity_per_crew_day)
    result = simulate(requests, 0, 0, calendar.n_days - 1, capacity)

    rows, open_start = [], 0
    for m in range(1, 13):
        d = dept_plan.decision(m)
        prev = dept_plan.decision(m - 1) if m > 1 else MonthDecision(0)
        st = period_stats(result, calendar.month_first_day[m], calendar.month_last_day[m])
        paid = crews[m] + (d.hires_ordered if config.PAID_TRAINING else 0)
        regular_cost = paid * dept.monthly_cost
        seasonal_cost = d.seasonal_crews * config.SEASONAL_COST_MULTIPLIER * dept.monthly_cost
        severance = d.releases_noticed * config.SEVERANCE_FRACTION * dept.annual_cost
        overdue_pen = st.overdue_events * config.OVERDUE_PENALTY
        long_pen = st.long_overdue_events * config.LONG_OVERDUE_PENALTY
        rows.append(
            StaffingRow(
                plan=plan_name,
                scenario=scenario,
                department=dept.code,
                month=m,
                hires_ordered=d.hires_ordered,
                hires_started=prev.hires_ordered,
                releases_noticed=d.releases_noticed,
                releases_effective=prev.releases_noticed,
                regular_crews=crews[m],
                seasonal_crews=d.seasonal_crews,
                capacity=working[m] * dept.capacity_per_crew_day * calendar.service_days_in_month(m),
                open_start=open_start,
                arrivals=st.arrivals,
                closed=st.closed,
                closed_on_time=st.closed_on_time,
                late_completions=st.late_completions,
                no_target_closed=st.no_target_closed,
                overdue_events=st.overdue_events,
                long_overdue_events=st.long_overdue_events,
                open_end=st.open_end,
                open_overdue_end=st.open_overdue_end,
                open_long_overdue_end=st.open_long_overdue_end,
                open_not_yet_due_end=st.open_not_yet_due_end,
                open_no_target_end=st.open_no_target_end,
                regular_cost=regular_cost,
                seasonal_cost=seasonal_cost,
                severance_cost=severance,
                overdue_penalty=overdue_pen,
                long_overdue_penalty=long_pen,
                total_cost=regular_cost + seasonal_cost + severance + overdue_pen + long_pen,
            )
        )
        open_start = st.open_end

    year_end = year_end_report(result, dept_plan, sum(r.total_cost for r in rows))
    return rows, year_end


def year_end_report(result: SimResult, dept_plan: DepartmentPlan, costs_accrued: float) -> YearEnd:
    """Classify what is still open at the end of the simulated year (spec 5.5).

    ``result`` must be a full-year simulation starting from an empty queue
    (head_start = 0), so it covers every request.

    * Open and past target, less than 30 days past: its $20 is already
      charged. Its 30-day mark falls in 2026, so the $100 is disclosed, not
      charged (both counts below refer to the same requests).
    * Open and 30+ days past target: $120 already charged.
    * Open with a 2026 target: not yet due; future exposure, no cost.
    """
    if result.head_start != 0:
        raise ValueError("year_end_report needs a full-year simulation from an empty queue")
    req = result.requests
    last = result.end_day
    close = result.close_day
    has_t, tgt, arr = req.has_target, req.target_day, req.arrival_day
    long_day = tgt + config.LONG_OVERDUE_DAYS
    open_end = (arr <= last) & (close > last)
    overdue_not_long = open_end & has_t & (tgt <= last) & (long_day > last)
    due = has_t & (tgt <= last)
    on_time = due & (close <= tgt)
    dec = dept_plan.decision(12)
    return YearEnd(
        department=dept_plan.department,
        costs_accrued=costs_accrued,
        open_overdue_charged=int(overdue_not_long.sum()),
        open_long_overdue_charged=int((open_end & has_t & (long_day <= last)).sum()),
        long_threshold_in_2026=int(overdue_not_long.sum()),
        not_yet_due=int((open_end & has_t & (tgt > last)).sum()),
        open_no_target=int((open_end & ~has_t).sum()),
        hires_ordered_effective_2026=dec.hires_ordered,
        notices_effective_2026=dec.releases_noticed,
        due_in_2025=int(due.sum()),
        on_time_rate=float(on_time.sum() / due.sum()) if due.sum() else float("nan"),
    )


# ---------------------------------------------------------------------------
# Summaries for the report
# ---------------------------------------------------------------------------


def summarize(rows: pd.DataFrame, year_ends: list[YearEnd]) -> pd.DataFrame:
    """Annual totals per department for one plan and scenario, plus an ALL row.

    Columns: plan, scenario, department, staff_cost (regular + seasonal +
    severance), penalty_cost, total_cost, overdue_events,
    long_overdue_events, on_time_rate (share of 2025-due requests closed by
    their target day), open_dec31.
    """
    ye = {y.department: y for y in year_ends}
    out = []
    for dept, g in rows.groupby("department", sort=False):
        out.append(
            {
                "plan": g["plan"].iloc[0],
                "scenario": g["scenario"].iloc[0],
                "department": dept,
                "staff_cost": g[["regular_cost", "seasonal_cost", "severance_cost"]].to_numpy().sum(),
                "penalty_cost": g[["overdue_penalty", "long_overdue_penalty"]].to_numpy().sum(),
                "total_cost": g["total_cost"].sum(),
                "overdue_events": int(g["overdue_events"].sum()),
                "long_overdue_events": int(g["long_overdue_events"].sum()),
                "due_in_2025": ye[dept].due_in_2025,
                "on_time_rate": ye[dept].on_time_rate,
                "open_dec31": int(g.loc[g["month"] == 12, "open_end"].iloc[0]),
            }
        )
    df = pd.DataFrame(out)
    total = {
        "plan": df["plan"].iloc[0],
        "scenario": df["scenario"].iloc[0],
        "department": "ALL",
        **{c: df[c].sum() for c in ["staff_cost", "penalty_cost", "total_cost", "overdue_events", "long_overdue_events", "due_in_2025", "open_dec31"]},
    }
    total["on_time_rate"] = float((df["on_time_rate"] * df["due_in_2025"]).sum() / df["due_in_2025"].sum())
    return pd.concat([df, pd.DataFrame([total])], ignore_index=True)


FRONTIER_TARGETS: tuple[float, ...] = (0.50, 0.70, 0.80, 0.85, 0.90, 0.93, 0.95, 0.97, 1.00)


def seasonal_frontier(workloads: dict[str, Workload], targets: tuple[float, ...] = FRONTIER_TARGETS) -> pd.DataFrame:
    """Parks cost vs. on-time for a range of seasonal service targets.

    This is the evidence behind ``config.SEASONAL_ON_TIME_TARGET``. For each
    target, the whole plan is re-made on the planning workload (so later
    hiring reacts to the different seasonal choice) and Parks is scored on
    the base evaluation workload. A target of 1.00 means "remove every
    avoidable miss", the spec's original seasonal rule. The first row is the
    fixed-crew baseline.

    ``cost_per_extra_point`` is the extra Parks cost for each extra
    percentage point of annual on-time rate, compared with the row above: it
    shows where buying more service starts to get expensive.
    """
    def parks_row(label: str, plan: Plan) -> dict:
        rows, year_ends = score_plan(plan, workloads["base"], "base")
        s = summarize(rows, year_ends).set_index("department").loc[config.SEASONAL_DEPT]
        pf = plan.to_frame().query("department == @config.SEASONAL_DEPT")
        return {
            "rule": label,
            "parks_total_cost": float(s["total_cost"]),
            "parks_on_time_rate": float(s["on_time_rate"]),
            "seasonal_crew_months": int(pf["seasonal_crews"].sum()),
            "permanent_hires": int(pf["hires_ordered"].sum()),
        }

    out = [parks_row("baseline (January crews)", baseline_plan())]
    saved = config.SEASONAL_ON_TIME_TARGET
    try:
        for target in targets:
            config.SEASONAL_ON_TIME_TARGET = target
            label = "every avoidable miss" if target >= 1 else f"floor {target:.0%}"
            out.append(parks_row(label, make_plan(workloads["planning"])))
    finally:
        config.SEASONAL_ON_TIME_TARGET = saved  # never leave the global changed
    df = pd.DataFrame(out)
    d_cost = df["parks_total_cost"].diff()
    d_points = df["parks_on_time_rate"].diff() * 100
    df["cost_per_extra_point"] = (d_cost / d_points).where(d_points > 0)
    df["chosen"] = df["rule"] == f"floor {saved:.0%}"
    return df


# ---------------------------------------------------------------------------
# Full-dataset reconciliation (spec section 9, check 8)
# ---------------------------------------------------------------------------


def reconciliation_failures(rows: pd.DataFrame, plan: Plan, workload: Workload) -> list[str]:
    """Check one scored plan + scenario against the accounting identities.

    Returns a list of human-readable failures (empty means every check
    passed). Run on every scenario and plan, not only on small fixtures.
    """
    fails: list[str] = []
    calendar = build_calendar()
    if len(rows) != 48:
        fails.append(f"expected 48 rows, got {len(rows)}")
    cost_parts = ["regular_cost", "seasonal_cost", "severance_cost", "overdue_penalty", "long_overdue_penalty"]
    totals = workload.monthly_totals(calendar).set_index(["department", "month"])["requests"]
    for dept in config.DEPT_CODES:
        r = rows[rows["department"] == dept].sort_values("month").reset_index(drop=True)
        dp = plan.departments[dept]
        prev_open, prev_crews = 0, None
        for _, x in r.iterrows():
            m = int(x["month"])
            where = f"{dept} month {m}"
            # Request flow.
            if x["open_start"] != prev_open:
                fails.append(f"{where}: open_start {x['open_start']} != previous open_end {prev_open}")
            if x["open_start"] + x["arrivals"] != x["closed"] + x["open_end"]:
                fails.append(f"{where}: start open + arrivals != closed + end open")
            if x["arrivals"] != int(totals.get((dept, m), 0)):
                fails.append(f"{where}: arrivals differ from the workload")
            parts = x["open_not_yet_due_end"] + x["open_overdue_end"] + x["open_long_overdue_end"] + x["open_no_target_end"]
            if parts != x["open_end"]:
                fails.append(f"{where}: month-end inventory does not partition open_end")
            if x["closed_on_time"] + x["late_completions"] + x["no_target_closed"] != x["closed"]:
                fails.append(f"{where}: closed does not split into on-time + late + no-target")
            # Workforce.
            if prev_crews is not None and x["regular_crews"] != prev_crews + x["hires_started"] - x["releases_effective"]:
                fails.append(f"{where}: crews(t) != crews(t-1) + hires_started - releases_effective")
            prev_dec = dp.decision(m - 1) if m > 1 else MonthDecision(0)
            if x["hires_started"] != prev_dec.hires_ordered or x["releases_effective"] != prev_dec.releases_noticed:
                fails.append(f"{where}: starts/leaves not matched to last month's orders/notices")
            if x["seasonal_crews"] and (dept != config.SEASONAL_DEPT or m not in config.SEASONAL_MONTHS):
                fails.append(f"{where}: seasonal crews outside Parks April-October")
            # Costs.
            if not np.isclose(sum(x[c] for c in cost_parts), x["total_cost"]):
                fails.append(f"{where}: cost components do not sum to total_cost")
            if x["overdue_penalty"] != x["overdue_events"] * config.OVERDUE_PENALTY:
                fails.append(f"{where}: overdue penalty != events x $20")
            if x["long_overdue_penalty"] != x["long_overdue_events"] * config.LONG_OVERDUE_PENALTY:
                fails.append(f"{where}: long-overdue penalty != events x $100")
            prev_open, prev_crews = x["open_end"], x["regular_crews"]
        # Penalties: per-request event counts, computed independently of the
        # monthly rows from one full-year simulation.
        req = workload.for_department(dept)
        crews = dp.regular_crews()
        working = {m: crews[m] + dp.decision(m).seasonal_crews for m in range(1, 13)}
        res = simulate(
            req, 0, 0, calendar.n_days - 1,
            daily_capacity_from_crews(calendar, working, config.DEPARTMENTS[dept].capacity_per_crew_day),
        )
        last = calendar.n_days - 1
        expect_overdue = int((req.has_target & (req.target_day <= last) & (res.close_day > req.target_day)).sum())
        long_day = req.target_day + config.LONG_OVERDUE_DAYS
        expect_long = int((req.has_target & (long_day <= last) & (res.close_day > long_day)).sum())
        if r["overdue_events"].sum() != expect_overdue:
            fails.append(f"{dept}: overdue events {r['overdue_events'].sum()} != requests overdue in 2025 {expect_overdue}")
        if r["long_overdue_events"].sum() != expect_long:
            fails.append(f"{dept}: long-overdue events {r['long_overdue_events'].sum()} != {expect_long}")
        if r["arrivals"].sum() != len(req):
            fails.append(f"{dept}: annual arrivals != workload total")
    return fails


def score_plan(plan: Plan, workload: Workload, scenario: str) -> tuple[pd.DataFrame, list[YearEnd]]:
    """Replay a frozen plan on a workload: 48 StaffingRows plus year-end reports."""
    calendar = build_calendar()
    rows, year_ends = [], []
    for dept in config.DEPT_CODES:
        r, ye = score_department(plan.departments[dept], workload.for_department(dept), plan.name, scenario, calendar)
        rows += r
        year_ends.append(ye)
    return pd.DataFrame([r.model_dump() for r in rows]), year_ends
