"""Shared pytest fixtures.

Building the real 2025 workloads and the frozen plan takes a few seconds, so
they are built once per test session ("session" scope) and reused by every
test that asks for them. They read only the committed tables in
data/processed/, so the tests need no network and no API key.
"""

from __future__ import annotations

import pytest

from boston311 import forecast, staffing, workload
from boston311.simulate import build_calendar


@pytest.fixture(scope="session")
def calendar():
    return build_calendar()


@pytest.fixture(scope="session")
def forecast_2025():
    return forecast.forecast_2025()


@pytest.fixture(scope="session")
def workloads(forecast_2025):
    """Planning + four evaluation workloads built from the committed data."""
    return workload.build_all_workloads(forecast_2025)


@pytest.fixture(scope="session")
def frozen_plan(workloads):
    return staffing.make_plan(workloads["planning"])
