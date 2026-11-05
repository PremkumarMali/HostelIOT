"""Live in-memory store: latest reading + last 60 min per device, KPIs, alerts, notifications.

InfluxDB keeps the full history (written by the ingestion code). The dashboard only needs
"now" and the last hour, so the backend serves those from memory, which keeps it fast and simple.
ponytail: memory only, so a backend restart empties the charts for ~2 min and forgets alerts;
persist alerts (SQLite / Influx) if a HACCP audit trail is needed.

All methods run on the asyncio thread (MQTT readings are handed over with call_soon_threadsafe),
so no locks are needed.
"""
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
HISTORY_LEN = 60          # readings kept per device = 60 simulated minutes


def load_yaml(name):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Store:
    def __init__(self):
        self.devices = load_yaml("devices.yaml")
        rules = load_yaml("alert_rules.yaml")["rules"]
        self.silent_min = rules["sensor_silent"]["silent_min"]
        self.high_flow_factor = rules["water_flow_high"]["factor_over_normal"]
        self.wasting_vacant_min = rules["hvac_vacant_running"]["vacant_min"]
        self.energy_cost = self.devices["property"]["energy_cost_per_kwh"]
        self.setback_c = self.devices["rooms"]["hvac"]["setback_c"]

        # Configured devices, so the dashboard shows every room even before data arrives
        self.rooms = {str(r): floor for floor, rs in self.devices["rooms"]["floors"].items() for r in rs}
        self.zones = {z["id"]: z for z in self.devices["water_zones"]}
        self.units = {u["id"]: u for u in self.devices["cold_units"]}
        self.reset()

    def reset(self):
        self.latest = {}          # device_id -> last payload
        self.history = {}         # device_id -> deque of payloads
        self.room_kwh = {}        # device_id -> HVAC kWh since start
        self.sim_now = None       # newest timestamp seen = the simulation clock
        self.first_ts = None      # first timestamp seen (start of monitoring)
        self.totals = dict(occ_min=0, occ_kwh=0.0, vacant_sold_min=0, vacant_kwh=0.0,
                           water_l=0.0, cold_total=0, cold_ok=0)
        self.alerts = {}          # alert id -> Alert
        self.notifications = []   # Notification, oldest first
        self.breach_eta = {}      # cold device_id -> minutes until predicted breach (set by the AI engine)
        self.dirty = True         # summary changed since last WebSocket push

    # ---------- incoming data ----------
    def update(self, p):
        """Store one validated reading (a dict). Each reading = 1 simulated minute."""
        did = p["device_id"]
        ts = datetime.fromisoformat(p["ts"])
        if self.sim_now is None or ts > self.sim_now:
            self.sim_now = ts
        if self.first_ts is None:
            self.first_ts = ts
        self.latest[did] = p
        self.history.setdefault(did, deque(maxlen=HISTORY_LEN)).append(p)

        t = self.totals
        if p["type"] == "thermostat":
            kwh = p["hvac_kw"] / 60                  # kW for 1 minute
            self.room_kwh[did] = self.room_kwh.get(did, 0.0) + kwh
            if p["occupied"]:
                t["occ_min"] += 1
                t["occ_kwh"] += kwh
            elif p["pms_sold"]:
                t["vacant_sold_min"] += 1
                t["vacant_kwh"] += kwh
        elif p["type"] == "water":
            t["water_l"] += p["flow_lpm"]            # L/min for 1 minute
        else:
            t["cold_total"] += 1
            t["cold_ok"] += p["safe_min_c"] <= p["temp_c"] <= p["safe_max_c"]
        self.dirty = True

    # ---------- statuses ----------
    def offline(self, did):
        if self.sim_now is None:
            return False                             # no data at all yet
        p = self.latest.get(did)
        last = datetime.fromisoformat(p["ts"]) if p else self.first_ts   # never seen: silent since start
        return self.sim_now - last >= timedelta(minutes=self.silent_min)

    def device_ids(self):
        return ([f"thermo-{r}" for r in self.rooms] + [z["device_id"] for z in self.zones.values()]
                + [u["device_id"] for u in self.units.values()])

    def locate(self, did):
        """device_id -> (dashboard section, human location, room number or None)."""
        pretty = lambda area: area.replace("floor", "Floor ").title()          # "floor2" -> "Floor 2"
        if did.startswith("thermo-") and did[7:] in self.rooms:
            room = did[7:]
            return "Guest rooms", f"Room {room} · {pretty(self.rooms[room])}", room
        for z in self.zones.values():
            if z["device_id"] == did:
                return "Water & leaks", f"{z['name']} · {pretty(z['area'])}", None
        for u in self.units.values():
            if u["device_id"] == did:
                return "Kitchen cold chain", f"{u['name']} · {pretty(u['area'])}", None
        return "Sensors", did, None

    def silent_devices(self):
        """device_id -> whole minutes without data, for every configured device that is offline."""
        out = {}
        for did in self.device_ids():
            if self.offline(did):
                p = self.latest.get(did)
                last = datetime.fromisoformat(p["ts"]) if p else self.first_ts
                out[did] = int((self.sim_now - last).total_seconds() // 60)
        return out

    def has_open_alert(self, did):
        return any(a.source == did and a.status == "open" for a in self.alerts.values())

    def room_status(self, did, p):
        if self.offline(did):
            return "offline"
        if not p:
            return "no_data"
        if self.has_open_alert(did):
            return "fault"
        if (p["hvac_on"] and not p["occupied"] and p["vacant_min"] >= self.wasting_vacant_min
                and p["temp_c"] < self.setback_c - 1):
            return "wasting"                         # cooling an empty room below setback
        if p["occupied"]:
            return "guest_in"
        return "sold_out" if p["pms_sold"] else "unsold"

    def water_status(self, did, p, normal):
        if self.offline(did):
            return "offline"
        if not p:
            return "no_data"
        if p["leak_wet"]:
            return "leak"
        return "high" if p["flow_lpm"] > self.high_flow_factor * normal else "ok"

    def cold_status(self, did, p):
        if self.offline(did):
            return "offline"
        if not p:
            return "no_data"
        if not p["safe_min_c"] <= p["temp_c"] <= p["safe_max_c"]:
            return "breach"
        if p["door_open"]:
            return "door_open"
        if did in self.breach_eta:                   # the AI trend forecast predicts a breach soon
            return "at_risk"
        return "ok"

    # ---------- views for the API ----------
    def room_view(self, room):
        did = f"thermo-{room}"
        p = self.latest.get(did, {})
        return {**p, "device_id": did, "room": room, "area": self.rooms[room],
                "kwh": round(self.room_kwh.get(did, 0.0), 3), "status": self.room_status(did, p)}

    def water_view(self, zone_id):
        z = self.zones[zone_id]
        p = self.latest.get(z["device_id"], {})
        return {**p, "device_id": z["device_id"], "zone": zone_id, "name": z["name"], "area": z["area"],
                "normal_flow_lpm": z["normal_flow_lpm"],
                "status": self.water_status(z["device_id"], p, z["normal_flow_lpm"])}

    def cold_view(self, unit_id):
        u = self.units[unit_id]
        p = self.latest.get(u["device_id"], {})
        return {**p, "device_id": u["device_id"], "unit": unit_id, "name": u["name"], "area": u["area"],
                "safe_min_c": u["safe_min_c"], "safe_max_c": u["safe_max_c"],
                "breach_in_min": self.breach_eta.get(u["device_id"]),
                "status": self.cold_status(u["device_id"], p)}

    def device_view(self, p):
        """View for the device that sent payload p (used for WebSocket pushes)."""
        if p["type"] == "thermostat" and p["room"] in self.rooms:
            return "room", self.room_view(p["room"])
        if p["type"] == "water" and p["zone"] in self.zones:
            return "water", self.water_view(p["zone"])
        if p["type"] == "cold_chain" and p["unit"] in self.units:
            return "cold_chain", self.cold_view(p["unit"])
        return None, None                            # device not in config/devices.yaml

    def history_of(self, did):
        return list(self.history.get(did, []))

    def water_total_history(self):
        """Total flow of all zones per simulated minute."""
        totals = {}
        for z in self.zones.values():
            for p in self.history.get(z["device_id"], []):
                totals[p["ts"]] = totals.get(p["ts"], 0.0) + p["flow_lpm"]
        return [{"ts": ts, "flow_lpm": round(v, 2)} for ts, v in sorted(totals.items())]

    def summary(self):
        t = self.totals
        rooms = [self.room_view(r) for r in self.rooms]
        # Energy saved: what vacant sold rooms WOULD have used at the occupied rate, minus what they used
        rate = t["occ_kwh"] / t["occ_min"] if t["occ_min"] else 0.0
        saved_kwh = max(0.0, rate * t["vacant_sold_min"] - t["vacant_kwh"])
        open_alerts = [a for a in self.alerts.values() if a.status == "open"]
        all_ids = self.device_ids()
        return {
            "sim_time": self.sim_now.isoformat() if self.sim_now else None,
            "streams": len(self.latest),
            "rooms_total": len(rooms),
            "rooms_sold": sum(bool(r.get("pms_sold")) for r in rooms),
            "guests_in": sum(bool(r.get("occupied")) for r in rooms),
            "hvac_kwh": round(sum(self.room_kwh.values()), 2),
            "energy_saved_kwh": round(saved_kwh, 2),
            "energy_saved_inr": round(saved_kwh * self.energy_cost),
            "water_used_l": round(t["water_l"]),
            "cold_compliance_pct": round(100 * t["cold_ok"] / t["cold_total"], 1) if t["cold_total"] else None,
            "open_alerts": len(open_alerts),
            "critical_alerts": sum(a.severity == "critical" for a in open_alerts),
            "messages_sent": sum(n.status != "failed" for n in self.notifications),
            "offline": [d for d in all_ids if self.offline(d)],
        }

    def snapshot(self):
        prop = self.devices["property"]
        return {
            "property": {"name": prop["name"], "energy_cost_per_kwh": prop["energy_cost_per_kwh"]},
            "summary": self.summary(),
            "rooms": [self.room_view(r) for r in self.rooms],
            "water": [self.water_view(z) for z in self.zones],
            "cold_chain": [self.cold_view(u) for u in self.units],
            "alerts": [a.model_dump(mode="json") for a in self.alerts.values()],
            "notifications": [n.model_dump(mode="json") for n in self.notifications[-50:]],
        }

    # ---------- alerts (Phase 7's alert manager adds them) ----------
    def add_alert(self, alert):
        self.alerts[alert.id] = alert
        self.dirty = True

    def ack(self, alert_id, by, at):
        alert = self.alerts.get(alert_id)
        if alert and alert.status == "open":
            alert.status, alert.acked_by, alert.acked_at = "acknowledged", by, at
            self.dirty = True
        return alert

    def add_notification(self, n):
        self.notifications.append(n)
        self.dirty = True


store = Store()
