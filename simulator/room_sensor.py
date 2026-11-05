"""Demo 1: guest-room thermostat with a built-in occupancy (PIR) sensor.

Every step() = 1 simulated minute. The model is deliberately simple:
  - occupancy: a sold room's guest comes and goes, more likely in at night
  - thermostat: comfort setpoint while the guest is around, setback once vacant 10 min
  - temperature: drifts toward the outdoor temperature, the AC pulls it down
"""
import math
import random

SUPPLY_AIR_C = 14.0   # air coming out of the AC unit


def outdoor_temp(hour):
    """Bengaluru-like day: about 20 °C at 3 am and 30 °C at 3 pm."""
    return 25 + 5 * math.sin(2 * math.pi * (hour - 9) / 24)


def chance_in_room(hour):
    """Probability that the guest of a sold room is in the room at this hour."""
    if hour >= 22 or hour < 7:
        return 0.9   # sleeping
    if 9 <= hour < 17:
        return 0.3   # out for the day
    return 0.6       # morning / evening


class RoomSensor:
    FAULTS = {"hvac_stuck_on"}  # faults the injector may set on this sensor

    def __init__(self, room, floor, prop, hvac_cfg):
        self.key = str(room)                     # how the fault injector finds it
        self.device_id = f"thermo-{room}"
        self.topic = f"dt/hotel/{prop}/{floor}/{room}/{self.device_id}/telemetry"
        self.cfg = hvac_cfg
        self.fault = None
        self.offline = False

        self.pms_sold = random.random() < 0.7    # PMS: ~70% of rooms sold tonight
        self.occupied = None                     # decided on the first step
        self.vacant_min = 30
        self.temp_c = random.uniform(23, 26)
        self.hvac_on = False
        self.battery_pct = random.uniform(60, 100)

    def step(self, now):
        hour = now.hour + now.minute / 60

        # 0. PMS: rooms are re-sold every day at 12:00 check-out
        if now.hour == 12 and now.minute == 0:
            self.pms_sold = random.random() < 0.7

        # 1. Occupancy: about every 30 min the guest may arrive or leave
        if not self.pms_sold:
            self.occupied = False
        elif self.occupied is None or random.random() < 0.03:
            self.occupied = random.random() < chance_in_room(hour)
        if self.fault == "hvac_stuck_on":
            self.occupied = False                # the demo fault: AC on in an EMPTY room
        self.vacant_min = 0 if self.occupied else self.vacant_min + 1

        # 2. Thermostat with ±0.5 °C hysteresis. Unsold rooms keep the AC off.
        if self.pms_sold:
            in_use = self.vacant_min < self.cfg["setback_after_vacant_min"]
            setpoint = self.cfg["setpoint_c"] if in_use else self.cfg["setback_c"]
            if self.temp_c > setpoint + 0.5:
                self.hvac_on = True
            elif self.temp_c < setpoint - 0.5:
                self.hvac_on = False
        else:
            setpoint = self.cfg["setback_c"]
            self.hvac_on = False
        if self.fault == "hvac_stuck_on":
            self.hvac_on = True                  # relay stuck: ignores the setpoint

        # 3. Room temperature: slowly pulled toward outdoor + 2 °C (sun, people); the AC pulls it
        #    toward its ~14 °C supply air. Rates calibrated so minute-to-minute changes match the
        #    real UCI room sensor data (see ml/evaluation_report.md).
        self.temp_c += 0.004 * (outdoor_temp(hour) + 2 - self.temp_c)
        if self.hvac_on:
            self.temp_c += 0.02 * (SUPPLY_AIR_C - self.temp_c)
        self.temp_c += random.gauss(0, 0.015)    # sensor noise

        humidity = 70 - 1.5 * (outdoor_temp(hour) - 20) - (6 if self.hvac_on else 0)
        self.battery_pct -= 0.0005

        return {
            "device_id": self.device_id,
            "type": "thermostat",
            "room": self.key,
            "ts": now.isoformat(timespec="seconds"),
            "temp_c": round(self.temp_c, 2),
            "setpoint_c": setpoint,
            "humidity_rh": round(humidity + random.gauss(0, 1), 1),
            "occupied": self.occupied,
            "vacant_min": self.vacant_min,
            "hvac_on": self.hvac_on,
            "hvac_kw": self.cfg["cooling_kw"] if self.hvac_on else 0.0,
            "pms_sold": self.pms_sold,
            "battery_pct": round(self.battery_pct, 1),
        }
