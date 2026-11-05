"""Demo 3: fridge / freezer temperature probe + door contact.

The compressor keeps the unit within ±1 °C of the middle of its safe band.
The unit always warms slowly, faster with the door open; the compressor cools it.
  compressor_failure -> compressor never runs, temperature drifts up out of band
  door_left_open     -> door stays open, temperature climbs
"""
import random

WARM_PER_MIN = 0.10   # heat leaking in through the walls
DOOR_PER_MIN = 0.50   # extra heat while the door is open
COOL_PER_MIN = 0.35   # compressor cooling


class ColdChainSensor:
    FAULTS = {"compressor_failure", "door_left_open"}

    def __init__(self, unit, prop):
        self.key = unit["id"]
        self.device_id = unit["device_id"]
        self.topic = f"dt/hotel/{prop}/{unit['area']}/{unit['id']}/{self.device_id}/telemetry"
        self.safe_min, self.safe_max = unit["safe_min_c"], unit["safe_max_c"]
        self.target = (self.safe_min + self.safe_max) / 2
        self.fault = None
        self.offline = False
        self.temp_c = self.target
        self.compressor_on = False
        self.door_min_left = 0
        self.battery_pct = random.uniform(60, 100)

    def step(self, now):
        # Door: staff open it more often during kitchen hours, for 1-2 minutes
        busy = 7 <= now.hour < 23
        if self.door_min_left > 0:
            self.door_min_left -= 1
        elif random.random() < (0.05 if busy else 0.005):
            self.door_min_left = random.randint(1, 2)
        door_open = self.door_min_left > 0 or self.fault == "door_left_open"

        # Compressor thermostat (±1 °C around the target)
        if self.temp_c > self.target + 1:
            self.compressor_on = True
        elif self.temp_c < self.target - 1:
            self.compressor_on = False
        if self.fault == "compressor_failure":
            self.compressor_on = False

        self.temp_c += WARM_PER_MIN
        if door_open:
            self.temp_c += DOOR_PER_MIN
        if self.compressor_on:
            self.temp_c -= COOL_PER_MIN
        self.temp_c += random.gauss(0, 0.03)

        self.battery_pct -= 0.0005
        return {
            "device_id": self.device_id,
            "type": "cold_chain",
            "unit": self.key,
            "ts": now.isoformat(timespec="seconds"),
            "temp_c": round(self.temp_c, 2),
            "door_open": door_open,
            "safe_min_c": self.safe_min,
            "safe_max_c": self.safe_max,
            "battery_pct": round(self.battery_pct, 1),
        }
