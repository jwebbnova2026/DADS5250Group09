"""Tests for the equity analysis and the run manifest."""

from __future__ import annotations

import json

import pytest

from boston311 import config, equity, manifest
from boston311.data import load_processed


def test_equity_expected_on_time_sums_to_actual_per_department():
    """Indirect standardization: summed over every neighborhood of a department,
    expected on-time requests equal actual on-time requests exactly, because the
    citywide type rates are computed from the same requests."""
    t = equity.neighborhood_equity()
    t["actual"] = t["on_time_rate"] * t["with_target"]
    t["expected"] = t["expected_on_time_rate"] * t["with_target"]
    sums = t.groupby("department")[["actual", "expected"]].sum()
    # The table rounds rates to 3 decimals, so allow a 0.1% relative difference.
    assert ((sums["actual"] - sums["expected"]).abs() / sums["actual"]).max() < 0.001


def test_equity_covers_every_department_and_flags_small_groups():
    t = equity.neighborhood_equity()
    assert set(t["department"]) == set(config.DEPT_CODES)
    assert (t.loc[t["small_sample"], "with_target"] < equity.MIN_EQUITY_SAMPLE).all()
    ns = load_processed("neighborhood_stats")
    assert t["with_target"].sum() == ns["with_target"].sum()


def test_manifest_records_inputs_seeds_and_model():
    m = manifest.build_manifest("offline", outputs=[])
    json.dumps(m)  # must be JSON-serializable
    assert m["seeds"] == {"planning": config.PLANNING_SEED, "evaluation": config.EVALUATION_SEED}
    assert m["model"]["id"] == config.LLM_MODEL and m["training_cutoff"] == config.TRAINING_CUTOFF
    assert "data/catalog/catalog.json" in m["inputs"] and len(m["inputs"]["data/catalog/catalog.json"]) == 64
    assert m["parameters"]["SCENARIO_FACTORS"] == {"plus20": "6/5", "minus20": "4/5"}
    assert all(s["md5"] for s in m["sources"])


@pytest.mark.parametrize("year", config.DATA_YEARS)
def test_sources_are_pinned(year):
    m = manifest.build_manifest("offline", outputs=[])
    src = {s["year"]: s for s in m["sources"]}[year]
    assert src["resource_id"] == config.RESOURCE_IDS[year]
