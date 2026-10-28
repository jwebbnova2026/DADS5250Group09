"""Daily first-in-first-out (FIFO) queue simulator and penalty events.

Spec section 4.3. This module is the single source of truth for how a
department's queue behaves. Every plan (our heuristic plan and the
fixed-workforce baseline) and every projection the planner makes runs
through :func:`simulate`.

The model in plain words
------------------------
* Each request arrives on a calendar day and joins the back of one queue per
  department.
* On a *service day*, the department closes requests from the front of the
  queue, up to its capacity for that day (crews x requests per crew-day).
* At the end of each day, every still-open request whose target day is today
  incurs a one-time $20 "overdue" event, and every still-open request whose
  target day was 30 days ago incurs a one-time extra $100 "long overdue" event.

Why the queue can be described by one number
--------------------------------------------
Requests are closed strictly in arrival order (ties broken by generation
sequence number). If we sort a department's requests that way, the requests
closed so far are always exactly the first ``head`` requests in the list, and
the open queue is the slice ``[head, arrived_so_far)``. So the whole queue
state at any moment is the single integer ``head``. Copying the planner's
queue for a projection (spec 4.4) means copying one integer, and the
simulator only needs to track how ``head`` moves day by day. From that we can
work out the exact day each request closed, and from close days we get every
penalty event and monthly count.

Day numbering
-------------
Day 0 is January 1, 2025 and day 364 is December 31, 2025. Target days can be
larger than 364 (deadlines in 2026); those requests can never become overdue
within the simulated year.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from boston311 import config

# A close day used for requests that are still open at the end of the
# simulated period. It is larger than any real day, so "close_day > d" is True.
NEVER = np.iinfo(np.int64).max // 4

# ---------------------------------------------------------------------------
# Synthetic 21-day operating calendar (spec 4.3, DEFAULT)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Calendar:
    """The planning year's days, months, and service days.

    Attributes:
        year: calendar year (2025).
        dates: the date of every day index (``dates[0]`` is January 1).
        month_of_day: month number 1-12 for every day index.
        service: True where the day is a service day (crews work).
        month_first_day / month_last_day: day index of each month's first and
            last calendar day, indexed by month number (index 0 unused).
    """

    year: int
    dates: tuple[date, ...]
    month_of_day: np.ndarray
    service: np.ndarray
    month_first_day: tuple[int, ...]
    month_last_day: tuple[int, ...]

    @property
    def n_days(self) -> int:
        return len(self.dates)

    def day_index(self, d: date | str) -> int:
        """Day index of a date (``"2025-02-10"`` -> 40)."""
        if isinstance(d, str):
            d = date.fromisoformat(d)
        return (d - self.dates[0]).days

    def month_days(self, month: int) -> range:
        """All day indices of a month, as a range."""
        return range(self.month_first_day[month], self.month_last_day[month] + 1)

    def service_days_in_month(self, month: int) -> int:
        return int(self.service[self.month_first_day[month] : self.month_last_day[month] + 1].sum())


def build_calendar(year: int = config.PLAN_YEAR, service_days: int = config.SERVICE_DAYS_PER_MONTH) -> Calendar:
    """Build the synthetic operating calendar for one year.

    Rules (spec 4.3):
    * Service days are the first ``service_days`` (21) weekdays of each month.
    * If a month has fewer weekdays than that, Saturdays are added, earliest
      first, until there are 21. (In 2025 only February needs this: it has 20
      weekdays, so Saturday February 1 becomes a service day.)
    * Weekdays after the 21st are non-service days. Holidays are ignored.
    """
    start = date(year, 1, 1)
    n_days = (date(year + 1, 1, 1) - start).days
    dates = tuple(start + timedelta(days=i) for i in range(n_days))
    month_of_day = np.array([d.month for d in dates], dtype=np.int64)
    service = np.zeros(n_days, dtype=bool)
    first, last = [0] * 13, [0] * 13
    for month in range(1, 13):
        idx = [i for i, d in enumerate(dates) if d.month == month]
        first[month], last[month] = idx[0], idx[-1]
        weekdays = [i for i in idx if dates[i].weekday() < 5]  # Monday=0 .. Friday=4
        saturdays = [i for i in idx if dates[i].weekday() == 5]
        chosen = weekdays[:service_days]
        if len(chosen) < service_days:
            chosen += saturdays[: service_days - len(chosen)]
        if len(chosen) < service_days:  # cannot happen for real months, but be explicit
            raise ValueError(f"Month {month} of {year} cannot supply {service_days} service days")
        service[chosen] = True
    return Calendar(year, dates, month_of_day, service, tuple(first), tuple(last))


# ---------------------------------------------------------------------------
# A department's requests in FIFO order
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requests:
    """One department's requests, sorted into the order they will be served.

    All arrays have the same length and are aligned: position ``i`` describes
    the ``i``-th request in FIFO order (by arrival day, then sequence number).

    Attributes:
        arrival_day: day index the request arrives.
        has_target: True for valid-target requests; False for no-target
            requests (classes "missing" and "invalid_ordering").
        target_day: day index of the target date; meaningless where
            ``has_target`` is False (stored as -1).
        seq: generation sequence number (unique; used for tie-breaking and to
            link a request back to its workload row).
    """

    arrival_day: np.ndarray
    has_target: np.ndarray
    target_day: np.ndarray
    seq: np.ndarray

    def __post_init__(self) -> None:
        n = len(self.arrival_day)
        if not (len(self.has_target) == len(self.target_day) == len(self.seq) == n):
            raise ValueError("Requests arrays must all have the same length")
        order_ok = np.all(
            (np.diff(self.arrival_day) > 0) | ((np.diff(self.arrival_day) == 0) & (np.diff(self.seq) > 0))
        )
        if n > 1 and not order_ok:
            raise ValueError("Requests must be sorted by (arrival_day, seq)")

    def __len__(self) -> int:
        return len(self.arrival_day)

    @classmethod
    def from_lists(cls, arrival_day, target_day, seq=None) -> "Requests":
        """Build from plain lists; use ``None`` as a target day for no-target.

        Handy for small hand-written test fixtures.
        """
        n = len(arrival_day)
        seq = np.arange(n) if seq is None else np.asarray(seq, dtype=np.int64)
        has_target = np.array([t is not None for t in target_day], dtype=bool)
        tgt = np.array([-1 if t is None else t for t in target_day], dtype=np.int64)
        order = np.lexsort((seq, np.asarray(arrival_day)))
        return cls(
            np.asarray(arrival_day, dtype=np.int64)[order], has_target[order], tgt[order], seq[order]
        )

    def arrived_through(self, day: int) -> int:
        """How many requests have arrived by the end of ``day`` (inclusive)."""
        return int(np.searchsorted(self.arrival_day, day, side="right"))


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimResult:
    """Outcome of simulating days ``start_day`` .. ``end_day`` (inclusive).

    Attributes:
        start_day, end_day: the simulated period.
        head_start: requests already closed before ``start_day``.
        head_end: requests closed by the end of ``end_day``. This is the queue
            state to carry into the next period.
        close_day: for every request at position ``head_start`` or later, the
            day it closed, or ``NEVER`` if still open at ``end_day``.
            ``close_day[k]`` belongs to request ``head_start + k``.
    """

    requests: Requests
    start_day: int
    end_day: int
    head_start: int
    head_end: int
    close_day: np.ndarray


def simulate(requests: Requests, head_start: int, start_day: int, end_day: int, daily_capacity: np.ndarray) -> SimResult:
    """Run the FIFO queue from ``start_day`` to ``end_day``.

    Args:
        requests: one department's requests in FIFO order.
        head_start: how many requests were already closed before
            ``start_day`` (0 at the start of the year).
        start_day, end_day: first and last day index to simulate, inclusive.
        daily_capacity: requests that can be closed on each day index. Must
            cover at least ``end_day + 1`` days; non-service days hold 0.

    Returns:
        A :class:`SimResult`.

    Daily order of events (spec 4.3), for each day d:
        1. Day d's arrivals join the back of the queue.
        2. If d is a service day, up to ``daily_capacity[d]`` requests close
           from the front.
        3-4. End-of-day penalty checks. These do not change the queue, so they
           are computed afterwards from each request's close day.
    """
    if end_day < start_day:
        raise ValueError("end_day must be on or after start_day")
    if len(daily_capacity) <= end_day:
        raise ValueError("daily_capacity does not cover the simulated period")
    if np.any(np.asarray(daily_capacity[start_day : end_day + 1]) < 0):
        raise ValueError("daily_capacity cannot be negative")

    head = head_start
    # heads[k] = number of requests closed by the end of day start_day + k.
    heads = np.empty(end_day - start_day + 1, dtype=np.int64)
    for k, d in enumerate(range(start_day, end_day + 1)):
        arrived = requests.arrived_through(d)  # step 1: arrivals are now in the queue
        head = min(head + int(daily_capacity[d]), arrived)  # step 2: close from the front
        heads[k] = head

    # A request at position i closed on the first day whose end-of-day head
    # count exceeds i. searchsorted finds that day for every request at once.
    # Only requests that closed by end_day (positions below the final head)
    # need the search; every later request is still open (NEVER).
    close_day = np.full(len(requests) - head_start, NEVER, dtype=np.int64)
    positions = np.arange(head_start, int(heads[-1]), dtype=np.int64)
    close_day[: len(positions)] = start_day + np.searchsorted(heads, positions, side="right")
    return SimResult(requests, start_day, end_day, head_start, int(heads[-1]), close_day)


@dataclass(frozen=True)
class PeriodStats:
    """Counts for one period of days (usually one month) of a simulation.

    Flow counts (what happened during the period):
        arrivals, closed, closed_on_time, late_completions, no_target_closed
    Penalty events during the period:
        overdue_events (the $20 event), long_overdue_events (the extra $100)
    Inventory at the end of the period's last day (these five partition
    ``open_end``; every open request is in exactly one):
        open_not_yet_due_end   - target day still in the future
        open_overdue_end       - past its target, not yet 30 days past
        open_long_overdue_end  - 30 or more days past its target
        open_no_target_end     - has no target date
    """

    arrivals: int
    closed: int
    closed_on_time: int
    late_completions: int
    no_target_closed: int
    overdue_events: int
    long_overdue_events: int
    open_end: int
    open_overdue_end: int
    open_long_overdue_end: int
    open_not_yet_due_end: int
    open_no_target_end: int

    @property
    def penalty_events(self) -> int:
        """Both kinds of penalty events together."""
        return self.overdue_events + self.long_overdue_events

    @property
    def penalty_cost(self) -> float:
        return self.overdue_events * config.OVERDUE_PENALTY + self.long_overdue_events * config.LONG_OVERDUE_PENALTY


def period_stats(result: SimResult, first_day: int, last_day: int) -> PeriodStats:
    """Summarize days ``first_day`` .. ``last_day`` of a simulation result.

    The period must lie inside the simulated period. Requests that closed
    before the simulation started (positions below ``head_start``) closed
    before ``first_day`` and can no longer cause events, so only positions
    from ``head_start`` onward are examined, plus arrival counts.
    """
    if first_day < result.start_day or last_day > result.end_day:
        raise ValueError("period must lie inside the simulated days")
    req = result.requests
    hs = result.head_start
    arr = req.arrival_day[hs:]
    has_t = req.has_target[hs:]
    tgt = req.target_day[hs:]
    close = result.close_day
    long_day = tgt + config.LONG_OVERDUE_DAYS

    arrivals = int(np.count_nonzero((req.arrival_day >= first_day) & (req.arrival_day <= last_day)))

    closed_mask = (close >= first_day) & (close <= last_day)
    # On time means closed on or before the target day (spec deadline table).
    on_time = closed_mask & has_t & (close <= tgt)
    late = closed_mask & has_t & (close > tgt)
    no_target_closed = closed_mask & ~has_t

    # Overdue event: at the end of the target day the request was still open,
    # i.e. it closed on a later day (or never). Same idea 30 days later.
    overdue = has_t & (tgt >= first_day) & (tgt <= last_day) & (close > tgt)
    long_overdue = has_t & (long_day >= first_day) & (long_day <= last_day) & (close > long_day)

    # Open at the end of last_day: arrived by then and not yet closed.
    open_end = (arr <= last_day) & (close > last_day)
    open_no_target = open_end & ~has_t
    open_not_yet_due = open_end & has_t & (tgt > last_day)
    open_long = open_end & has_t & (long_day <= last_day)
    open_overdue = open_end & has_t & (tgt <= last_day) & (long_day > last_day)

    return PeriodStats(
        arrivals=arrivals,
        closed=int(closed_mask.sum()),
        closed_on_time=int(on_time.sum()),
        late_completions=int(late.sum()),
        no_target_closed=int(no_target_closed.sum()),
        overdue_events=int(overdue.sum()),
        long_overdue_events=int(long_overdue.sum()),
        open_end=int(open_end.sum()),
        open_overdue_end=int(open_overdue.sum()),
        open_long_overdue_end=int(open_long.sum()),
        open_not_yet_due_end=int(open_not_yet_due.sum()),
        open_no_target_end=int(open_no_target.sum()),
    )


def open_at_start(requests: Requests, head: int, day: int) -> int:
    """Requests open at the *start* of ``day``: arrived before it, not yet closed."""
    return max(0, requests.arrived_through(day - 1) - head)


def daily_capacity_from_crews(
    calendar: Calendar, crews_by_month: dict[int, int] | list[int], capacity_per_crew_day: int
) -> np.ndarray:
    """Turn a crew count per month into a capacity per day.

    Args:
        calendar: the operating calendar (decides which days are service days).
        crews_by_month: total working crews (regular + seasonal) for each month
            number 1-12. A list is read as months 1..12 in order.
        capacity_per_crew_day: requests one crew closes per service day.

    Returns:
        An array with one entry per day of the year: crews x capacity on
        service days, 0 on non-service days.
    """
    if isinstance(crews_by_month, list):
        crews_by_month = {m + 1: c for m, c in enumerate(crews_by_month)}
    per_day = np.zeros(calendar.n_days, dtype=np.int64)
    for month, crews in crews_by_month.items():
        if crews < 0:
            raise ValueError(f"crews for month {month} cannot be negative (got {crews})")
        days = calendar.month_days(month)
        per_day[days.start : days.stop] = crews * capacity_per_crew_day
    return np.where(calendar.service, per_day, 0)
