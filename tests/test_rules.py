"""Layer 1 rules: each rule fires exactly when config/alert_rules.yaml says, and not before.

Run: python -m pytest tests/test_rules.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_engine.rules import offline_finding, run_rules  # noqa: E402

RULES = yaml.safe_load((ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8"))["rules"]
TS = "2026-10-24T22:30:00+05:30"


def cold(temp, door=False, battery=80):
    return {"device_id": "cold-walkin", "type": "cold_chain", "unit": "walkin", "ts": TS, "temp_c": temp,
            "door_open": door, "safe_min_c": 0, "safe_max_c": 5, "battery_pct": battery}


def water(flow, wet=False):
    return {"device_id": "water-laundry", "type": "water", "zone": "laundry", "ts": TS,
            "flow_lpm": flow, "leak_wet": wet, "battery_pct": 90}


def room(temp, setpoint=26.0, hvac=True, occupied=False, vacant=30):
    return {"device_id": "thermo-207", "type": "thermostat", "room": "207", "ts": TS, "temp_c": temp,
            "setpoint_c": setpoint, "humidity_rh": 55, "occupied": occupied, "vacant_min": vacant,
            "hvac_on": hvac, "hvac_kw": 1.1 if hvac else 0, "pms_sold": True, "battery_pct": 80}


def faults(history, normal=None):
    return [(f.fault_type, f.severity) for f in run_rules(history, "X", RULES, normal)]


def test_normal_readings_raise_nothing():
    assert faults([cold(2.5)] * 10) == []
    assert faults([water(9.0)] * 10, normal=9.0) == []
    assert faults([room(25.8)] * 10) == []                       # setback cooling, not below setpoint


def test_cold_breach_needs_3_minutes():
    assert faults([cold(2.5), cold(5.4), cold(5.6)]) == []        # only 2 minutes out of band
    assert faults([cold(5.2), cold(5.4), cold(5.6)]) == [("compressor_failure", "critical")]
    assert faults([cold(-0.5)] * 3) == [("compressor_failure", "critical")]   # too cold is a breach too


def test_door_open_needs_5_minutes():
    assert faults([cold(3.0, door=True)] * 4) == []
    assert faults([cold(3.0, door=True)] * 5) == [("door_left_open", "warning")]


def test_leak_probe_is_immediate_and_critical():
    assert faults([water(9.0, wet=True)], normal=9.0) == [("leak", "critical")]


def test_high_flow_needs_5_minutes():
    assert faults([water(19.0)] * 4, normal=9.0) == []
    assert faults([water(19.0)] * 5, normal=9.0) == [("leak", "warning")]


def test_ac_in_empty_room():
    assert faults([room(23.0, vacant=10)] * 3) == []              # setback not due yet
    assert faults([room(23.0, occupied=True, vacant=0)] * 3) == []   # guest is in
    assert faults([room(25.8), room(25.8), room(25.4)]) == []     # one reading of thermostat overshoot is normal
    assert faults([room(23.0, vacant=20)] * 3) == [("hvac_stuck_on", "warning")]


def test_battery_and_offline():
    assert faults([cold(2.5, battery=10)]) == [("battery_low", "warning")]
    f = offline_finding("cold-bar", "Bar fridge", 4, RULES)
    assert (f.fault_type, f.category, f.title) == ("sensor_offline", "sensor_offline", "Sensor offline: Bar fridge")


def test_alert_text_matches_the_brief():
    f = run_rules([water(21.3, wet=True)], "Laundry", RULES, 9.0)[0]
    assert f.title == "Water leak: Laundry"
    assert "Flow 21.3 L/min vs normal 9.0" in f.detail
    assert f.action == "Isolate the zone valve and send maintenance."
