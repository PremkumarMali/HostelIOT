"""End-to-end AI engine: simulator -> store -> detector (rules + ML + forecast) -> alert manager.

Each test runs the real simulator minute by minute, exactly like the live backend.
Needs the trained models (cd ml; python train_anomaly.py; python train_fault_classifier.py).

Run: python -m pytest tests/test_detector.py      (~1 min)
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "simulator")]
from ai_engine.alert_manager import AlertManager  # noqa: E402
from ai_engine.detector import Detector  # noqa: E402
from ai_engine.model_loader import ML_DIR, load_models  # noqa: E402
from backend.app.db import Store, load_yaml  # noqa: E402
from fault_injector import FaultInjector  # noqa: E402
from main import IST, build_sensors, load_config  # noqa: E402  (simulator)

if not (ML_DIR / "models" / "classifier_room.joblib").exists():
    pytest.skip("trained models missing: run the ml/ training scripts first", allow_module_level=True)

RULES = load_yaml("alert_rules.yaml")
MODELS = load_models()


class Hotel:
    """Simulator + store + detector + alert manager, advanced one minute at a time."""

    def __init__(self, seed=3, start="2026-10-24T09:00"):
        random.seed(seed)
        self.sensors = build_sensors(load_config())
        self.faults = FaultInjector(self.sensors)
        self.store = Store()
        self.detector = Detector(RULES, self.store.devices, MODELS)
        self.manager = AlertManager(self.store, RULES["escalation"]["critical_unacked_min"],
                                    RULES["escalation"]["resolve_after_min"])
        self.events = []
        self.manager.listeners.append(lambda ev, a: self.events.append((self.minute, ev, a.id, a.fault_type, a.source)))
        self.t = datetime.fromisoformat(start).replace(tzinfo=IST)
        self.minute = 0

    def run(self, minutes):
        for _ in range(minutes):
            self.minute += 1
            self.t += timedelta(minutes=1)
            for s in self.sensors:
                p = s.step(self.t)
                if not s.offline:
                    self.store.update(p)
            histories = {d: list(h) for d, h in self.store.history.items()}
            findings, eta = self.detector.detect(histories, self.store.silent_devices())
            self.store.breach_eta = eta
            self.manager.process(findings, self.store.sim_now)

    def first(self, event, fault, source):
        return next((e for e in self.events if e[1] == event and e[3] == fault and e[4] == source), None)


def test_quiet_when_nothing_is_wrong():
    h = Hotel()
    h.run(180)                                         # 3 hours of normal operation, 30 devices
    new = [e for e in h.events if e[1] == "new"]
    assert len(new) <= 1, new                          # at most one stray warning


def test_leak_alert_dedupe_escalation_and_resolve():
    h = Hotel()
    h.run(20)
    h.faults.inject("leak")                            # laundry
    start = h.minute
    h.run(15)
    leak = [e for e in h.events if e[3] == "leak" and e[4] == "water-laundry"]
    new = [e for e in leak if e[1] == "new"]
    assert len(new) == 1                               # one alert, however many layers saw it
    alert = h.store.alerts[new[0][2]]
    assert new[0][0] - start <= 3                      # detected within 3 sim minutes
    assert alert.severity == "critical" and "Flow" in alert.detail
    assert h.first("escalated", "leak", "water-laundry")   # critical + no ack for 10 min -> GM

    h.faults.clear()
    h.run(12)
    assert alert.status == "resolved"


def test_acknowledged_alert_is_not_escalated():
    h = Hotel()
    h.run(20)
    h.faults.inject("leak")
    h.run(4)
    alert_id = h.first("new", "leak", "water-laundry")[2]
    h.manager.acknowledge(alert_id, "Chief Engineer", h.store.sim_now)
    h.run(12)
    assert h.store.alerts[alert_id].status == "acknowledged"
    assert not h.first("escalated", "leak", "water-laundry")


def test_compressor_failure_is_forecast_before_the_breach():
    h = Hotel()
    h.run(20)
    h.faults.inject("compressor_failure")              # walk-in chiller
    h.run(45)
    new = h.first("new", "compressor_failure", "cold-walkin")
    upgraded = h.first("upgraded", "compressor_failure", "cold-walkin")
    assert new and upgraded and new[0] < upgraded[0]   # warning first, critical later, same alert
    assert new[2] == upgraded[2]
    assert h.store.alerts[new[2]].severity == "critical"


def test_ac_stuck_on_and_sensor_offline():
    h = Hotel()
    h.run(20)
    h.faults.inject("hvac_stuck_on")                   # room 207
    h.faults.inject("sensor_offline")                  # bar fridge
    start = h.minute
    h.run(30)
    ac = h.first("new", "hvac_stuck_on", "thermo-207")
    off = h.first("new", "sensor_offline", "cold-bar")
    assert ac and ac[0] - start <= 25
    assert off and off[0] - start <= 4
