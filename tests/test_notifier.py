"""Dashboard notifications: right section, right room / unit, right people, no duplicates.

Run: python -m pytest tests/test_notifier.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_engine.alert_manager import AlertManager  # noqa: E402
from ai_engine.rules import Finding  # noqa: E402
from backend.app.db import Store  # noqa: E402
from notifier.dashboard import DashboardNotifier  # noqa: E402

T0 = datetime.fromisoformat("2026-10-24T22:00:00+05:30")


def setup():
    store = Store()
    store.sim_now = T0
    sent = []
    manager = AlertManager(store, escalation_min=10, resolve_after_min=5)
    manager.listeners.append(DashboardNotifier(store, sent.append))
    return store, manager, sent


def finding(source, fault, category, severity="warning", title="X"):
    return Finding(source=source, fault_type=fault, category=category, severity=severity, method="rule",
                   confidence=0.99, title=title, detail="Some reading", action="Do something")


def run(store, manager, findings, minutes):
    for _ in range(minutes):
        store.sim_now += timedelta(minutes=1)
        manager.process(findings, store.sim_now)


def test_room_fault_names_section_and_room():
    store, manager, sent = setup()
    run(store, manager, [finding("thermo-207", "hvac_stuck_on", "room_energy", title="AC running in empty room: Room 207")], 3)
    assert len(sent) == 1                                    # one notification, not one per minute
    n = sent[0]["data"]
    assert n["section"] == "Guest rooms"
    assert n["location"] == "Room 207 · Floor 2" and n["room"] == "207"
    assert n["recipients"] == ["Duty Manager", "Chief Engineer"]
    assert n["text"].startswith("[WARNING] AC running in empty room: Room 207\nWhere: Guest rooms · Room 207 · Floor 2")


def test_leak_critical_escalates_to_gm_then_resolves():
    store, manager, sent = setup()
    leak = finding("water-laundry", "leak", "water", "critical", "Water leak: Laundry")
    run(store, manager, [leak], 11)
    events = [(m["data"]["event"], m["data"]["recipients"]) for m in sent]
    assert events[0] == ("new", ["Chief Engineer", "General Manager"])     # GM only because it is critical
    assert events[1] == ("escalated", ["General Manager"])
    assert sent[0]["data"]["location"] == "Laundry · Basement"
    run(store, manager, [], 6)                               # fault gone
    assert sent[-1]["data"]["event"] == "resolved" and sent[-1]["data"]["severity"] == "resolved"


def test_ack_stops_escalation_and_is_announced():
    store, manager, sent = setup()
    leak = finding("water-laundry", "leak", "water", "critical")
    run(store, manager, [leak], 2)
    manager.acknowledge(sent[0]["data"]["alert_id"], "Chief Engineer", store.sim_now)
    run(store, manager, [leak], 12)
    assert [m["data"]["event"] for m in sent] == ["new", "acknowledged"]
    assert "Acknowledged by Chief Engineer" in sent[1]["data"]["text"]


def test_cold_chain_unit_location_and_warning_routing():
    store, manager, sent = setup()
    run(store, manager, [finding("cold-walkin", "compressor_failure", "cold_chain")], 1)
    run(store, manager, [finding("cold-walkin", "compressor_failure", "cold_chain", "critical")], 1)
    assert [m["data"]["event"] for m in sent] == ["new", "upgraded"]
    assert sent[0]["data"]["section"] == "Kitchen cold chain"
    assert sent[0]["data"]["location"] == "Walk-in chiller · Kitchen"
    assert sent[0]["data"]["recipients"] == ["Executive Chef", "Chief Engineer"]
    assert len(store.notifications) == 2
