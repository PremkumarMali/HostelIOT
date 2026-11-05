"""Backend API checks without MQTT/Influx: feed simulator readings straight into the store.

Run: python -m pytest tests/test_backend.py
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "simulator")]
os.environ["MQTT_ENABLED"] = "false"                 # no broker in tests
os.environ["SIMULATOR_URL"] = "http://127.0.0.1:9"   # nothing listens here -> 503

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.db import store  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import Alert  # noqa: E402
from fault_injector import FaultInjector  # noqa: E402
from ingestion.schemas import parse  # noqa: E402
from main import IST, build_sensors, load_config  # noqa: E402  (simulator)


def feed(minutes, *faults):
    """Run the simulator for N minutes; every payload goes through the schema into the store."""
    random.seed(4)
    store.reset()
    sensors = build_sensors(load_config())
    injector = FaultInjector(sensors)
    for f in faults:
        injector.inject(f)
    t = datetime(2026, 10, 24, 8, 0, tzinfo=IST)
    for _ in range(minutes):
        t += timedelta(minutes=1)
        for s in sensors:
            p = s.step(t)
            if not s.offline:
                store.update(parse(json.dumps(p)).model_dump(mode="json"))


@pytest.fixture
def client():
    with TestClient(app) as c:                        # runs the lifespan (MQTT disabled)
        yield c


def test_empty_store_lists_every_configured_device(client):
    store.reset()
    rooms = client.get("/api/rooms").json()
    assert len(rooms) == 20 and {r["status"] for r in rooms} == {"no_data"}
    assert len(client.get("/api/water").json()) == 5
    assert len(client.get("/api/cold-chain").json()) == 5


def test_live_state_kpis_and_history(client):
    feed(90)
    s = client.get("/api/snapshot").json()["summary"]
    assert s["streams"] == 30 and s["offline"] == []
    assert 0 < s["rooms_sold"] <= 20 and s["water_used_l"] > 0
    assert s["cold_compliance_pct"] > 95
    assert len(client.get("/api/rooms/207/history").json()) == 60      # last 60 sim minutes
    assert len(client.get("/api/water/history").json()["total"]) == 60
    assert client.get("/api/rooms/999").status_code == 404


def test_fault_statuses(client):
    feed(40, "leak", "compressor_failure", "hvac_stuck_on", "sensor_offline")
    water = {z["zone"]: z["status"] for z in client.get("/api/water").json()}
    cold = {u["unit"]: u["status"] for u in client.get("/api/cold-chain").json()}
    room = client.get("/api/rooms/207").json()
    assert water["laundry"] == "leak"
    assert cold["walkin"] == "breach"
    assert cold["bar"] == "offline"
    assert room["status"] == "wasting"
    assert client.get("/api/snapshot").json()["summary"]["offline"] == ["cold-bar"]


def test_acknowledge_alert(client):
    feed(1)
    store.add_alert(Alert(id="a1", title="Water leak: Laundry", detail="Flow 21 vs 9", severity="critical",
                          confidence=0.9, method="rule", fault_type="leak", category="water",
                          action="Isolate valve", source="water-laundry", ts=store.sim_now))
    assert client.get("/api/snapshot").json()["summary"]["critical_alerts"] == 1
    r = client.post("/api/alerts/a1/ack", json={"by": "Chief Engineer"})
    assert r.json()["status"] == "acknowledged" and r.json()["acked_by"] == "Chief Engineer"
    assert client.get("/api/alerts?status=open").json() == []
    assert client.post("/api/alerts/nope/ack").status_code == 404


def test_websocket_snapshot(client):
    feed(2)
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "snapshot" and len(msg["data"]["rooms"]) == 20


def test_fault_endpoints(client):
    assert client.post("/api/sim/faults", json={"type": "meteor"}).status_code == 422
    assert client.post("/api/sim/faults", json={"type": "leak"}).status_code == 503   # simulator not running
