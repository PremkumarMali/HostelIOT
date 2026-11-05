"""Checks that the simulator behaves normally and that each demo fault shows in the data.

Run: python -m pytest tests/test_simulator.py
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "simulator"))
from fault_injector import FaultInjector  # noqa: E402
from main import IST, build_sensors, load_config  # noqa: E402


def run(minutes, *faults):
    """Simulate `minutes` from 08:00 with the given faults; return every published payload per device."""
    random.seed(1)
    sensors = build_sensors(load_config())
    injector = FaultInjector(sensors)
    for fault in faults:
        injector.inject(fault)
    t = datetime(2026, 10, 24, 8, 0, tzinfo=IST)
    history = {s.device_id: [] for s in sensors}
    for _ in range(minutes):
        t += timedelta(minutes=1)
        for s in sensors:
            payload = s.step(t)
            if not s.offline:
                history[s.device_id].append(payload)
    return injector, history


def test_normal_day_has_no_faults():
    _, h = run(24 * 60)
    for device, readings in h.items():
        assert len(readings) == 24 * 60
        if device.startswith("cold-"):
            assert all(r["safe_min_c"] <= r["temp_c"] <= r["safe_max_c"] for r in readings), device
        if device.startswith("water-"):
            assert not any(r["leak_wet"] for r in readings), device


def test_leak():
    _, h = run(5, "leak")
    last = h["water-laundry"][-1]
    assert last["leak_wet"]
    assert last["flow_lpm"] > 2 * 9.0           # well above the laundry's normal 9 L/min


def test_compressor_failure_breaches_band():
    _, h = run(40, "compressor_failure")
    assert h["cold-walkin"][-1]["temp_c"] > 5   # walk-in safe band is 0-5 °C


def test_hvac_stuck_on_in_empty_room():
    _, h = run(30, "hvac_stuck_on")
    last = h["thermo-207"][-1]
    assert last["hvac_on"] and not last["occupied"] and last["vacant_min"] >= 30


def test_sensor_offline_stops_publishing():
    injector, h = run(10, "sensor_offline")
    assert h["cold-bar"] == []
    assert {"device_id": "cold-bar", "fault": "sensor_offline"} in injector.active()
    injector.clear()
    assert injector.active() == []


def test_rejects_bad_faults():
    injector, _ = run(0)
    with pytest.raises(ValueError):
        injector.inject("leak", "207")           # a room has no leak probe
    with pytest.raises(ValueError):
        injector.inject("meteor")
