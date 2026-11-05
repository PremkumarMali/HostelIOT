"""Demo 2: water flow meter + leak probe for one hotel zone.

Normal flow follows a daily hotel pattern (morning and evening peaks).
A leak adds a constant extra flow; the floor probe turns wet 2 minutes later
(the time the water needs to reach it), so the flow anomaly shows first.
"""
import random

# Share of the zone's normal flow for each hour 0..23 (average ≈ 1.0)
HOUR_FACTOR = [0.3, 0.2, 0.2, 0.2, 0.3, 0.6, 1.2, 1.7, 1.8, 1.5, 1.2, 1.0,
               1.1, 1.0, 0.9, 0.9, 1.0, 1.2, 1.5, 1.6, 1.4, 1.0, 0.7, 0.4]

LEAK_EXTRA = 2.0       # demo leak adds 2x the zone's normal flow (ML data varies this)
PROBE_DELAY_MIN = 2    # minutes until the leak probe gets wet
PROBE_MIN_EXTRA = 0.8  # smaller leaks (drips) never reach the floor probe


class WaterSensor:
    FAULTS = {"leak"}

    def __init__(self, zone, prop):
        self.key = zone["id"]
        self.device_id = zone["device_id"]
        self.topic = f"dt/hotel/{prop}/{zone['area']}/{zone['id']}/{self.device_id}/telemetry"
        self.normal = zone["normal_flow_lpm"]
        self.fault = None
        self.offline = False
        self.leak_min = 0
        self.leak_extra = LEAK_EXTRA
        self.battery_pct = random.uniform(60, 100)

    def step(self, now):
        flow = self.normal * HOUR_FACTOR[now.hour] * random.uniform(0.8, 1.2)

        if self.fault == "leak":
            self.leak_min += 1
            flow += self.leak_extra * self.normal
        else:
            self.leak_min = 0

        self.battery_pct -= 0.0005
        return {
            "device_id": self.device_id,
            "type": "water",
            "zone": self.key,
            "ts": now.isoformat(timespec="seconds"),
            "flow_lpm": round(flow, 2),
            "leak_wet": self.leak_min >= PROBE_DELAY_MIN and self.leak_extra >= PROBE_MIN_EXTRA,
            "battery_pct": round(self.battery_pct, 1),
        }
