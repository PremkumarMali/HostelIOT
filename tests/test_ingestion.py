"""Ingestion checks: schemas accept simulator output, reject bad data, and build valid line protocol.

Run: python -m pytest tests/test_ingestion.py
"""
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "simulator")]
from ingestion.influx_writer import to_line  # noqa: E402
from ingestion.mqtt_consumer import handle  # noqa: E402
from main import IST, build_sensors, load_config  # noqa: E402  (simulator)


class FakeWriter:
    def __init__(self):
        self.lines = []

    def write(self, reading, area):
        self.lines.append(to_line(reading, area))


def test_every_simulator_message_is_accepted():
    random.seed(2)
    writer = FakeWriter()
    t = datetime(2026, 10, 24, 22, 30, tzinfo=IST)
    for s in build_sensors(load_config()):
        assert handle(s.topic, json.dumps(s.step(t)), writer) is None, s.device_id
    assert len(writer.lines) == 30


def test_line_protocol():
    writer = FakeWriter()
    msg = {"device_id": "cold-walkin", "type": "cold_chain", "unit": "walkin",
           "ts": "2026-10-24T22:30:00+05:30", "temp_c": 6, "door_open": False,
           "safe_min_c": 0, "safe_max_c": 5, "battery_pct": 77}
    handle("dt/hotel/blr01/kitchen/walkin/cold-walkin/telemetry", json.dumps(msg), writer)
    epoch = int(datetime(2026, 10, 24, 17, 0).replace(tzinfo=IST.utc).timestamp())  # 22:30 IST in UTC
    assert writer.lines == [
        "cold_chain,device_id=cold-walkin,location=walkin,area=kitchen "
        f"battery_pct=77.0,temp_c=6.0,door_open=f,safe_min_c=0.0,safe_max_c=5.0 {epoch}"
    ]   # ints became floats: Influx needs the same type on every write


def test_bad_messages_are_rejected():
    writer = FakeWriter()
    good = {"device_id": "water-laundry", "type": "water", "zone": "laundry",
            "ts": "2026-10-24T22:30:00+05:30", "flow_lpm": 9.1, "leak_wet": False, "battery_pct": 90}
    topic = "dt/hotel/blr01/basement/laundry/water-laundry/telemetry"
    bad_cases = [
        (topic, "not json"),
        (topic, json.dumps({**good, "flow_lpm": -3})),                 # negative flow
        (topic, json.dumps({**good, "battery_pct": 140})),             # out of range
        (topic, json.dumps({**good, "ts": "2026-10-24T22:30:00"})),    # no timezone
        (topic, '{"device_id":"water-laundry","type":"water","zone":"laundry","ts":"2026-10-24T22:30:00+05:30",'
                '"flow_lpm":NaN,"leak_wet":false,"battery_pct":90}'),  # NaN
        (topic, json.dumps({**good, "type": "toaster"})),              # unknown type
        (topic.replace("water-laundry/", "water-kitchen/"), json.dumps(good)),  # topic/device mismatch
        ("dt/hotel/blr01/oops", json.dumps(good)),                     # bad topic
    ]
    for t, raw in bad_cases:
        assert handle(t, raw, writer) is not None, raw
    assert writer.lines == []
