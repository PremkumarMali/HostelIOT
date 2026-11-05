"""Layer 1: fixed rules from config/alert_rules.yaml.

Rules are simple and explainable, and they never miss the obvious (a wet leak probe,
a fridge out of its safe band). They raise most of the CRITICAL alerts; the ML layers
add earlier and subtler WARNINGS.

Every layer reports a Finding; the alert manager turns findings into alerts.
"""
from dataclasses import dataclass

CATEGORY = {"thermostat": "room_energy", "water": "water", "cold_chain": "cold_chain"}

TITLES = {
    "leak": "Water leak: {name}",
    "compressor_failure": "Cold chain fault: {name}",
    "door_left_open": "Door left open: {name}",
    "hvac_stuck_on": "AC running in empty room: {name}",
    "sensor_offline": "Sensor offline: {name}",
    "battery_low": "Battery low: {name}",
    "anomaly": "Unusual readings: {name}",
}


@dataclass
class Finding:
    source: str          # device_id
    fault_type: str
    category: str        # routing key for notifications
    severity: str        # warning | critical
    method: str          # rule | classifier | forecast | anomaly
    confidence: float    # 0-1
    title: str
    detail: str
    action: str


def reading_summary(p, normal_flow=None):
    """One line describing the latest reading, used in every alert detail."""
    if p["type"] == "water":
        wet = ", leak probe WET" if p["leak_wet"] else ""
        return f"Flow {p['flow_lpm']:.1f} L/min vs normal {normal_flow:.1f}{wet}"
    if p["type"] == "cold_chain":
        door = ", door open" if p["door_open"] else ""
        return f"{p['temp_c']:.1f} °C (safe {p['safe_min_c']:g} to {p['safe_max_c']:g} °C){door}"
    who = "guest in room" if p["occupied"] else f"vacant {p['vacant_min']} min"
    return (f"{p['temp_c']:.1f} °C vs setpoint {p['setpoint_c']:.1f} °C, "
            f"AC {'on' if p['hvac_on'] else 'off'}, {who}")


def make_finding(p, name, fault_type, method, severity, confidence, action, note, normal_flow=None, title=None):
    detail = f"{note}. {reading_summary(p, normal_flow)}" if note else reading_summary(p, normal_flow)
    category = "sensor_offline" if fault_type in ("sensor_offline", "battery_low") else CATEGORY[p["type"]]
    return Finding(source=p["device_id"], fault_type=fault_type, category=category, severity=severity,
                   method=method, confidence=round(float(confidence), 2),
                   title=title or TITLES[fault_type].format(name=name), detail=detail, action=action)


def run_rules(history, name, rules, normal_flow=None):
    """Check one device's recent readings (oldest first) against every rule that applies."""
    p = history[-1]
    found = []

    def last(n):
        return history[-n:] if len(history) >= n else None

    def add(key, note):
        r = rules[key]
        found.append(make_finding(p, name, r["fault_type"], "rule", r["severity"], 0.99, r["action"], note, normal_flow))

    if p["type"] == "cold_chain":
        n = rules["cold_out_of_band"]["duration_min"]
        w = last(n)
        if w and all(not x["safe_min_c"] <= x["temp_c"] <= x["safe_max_c"] for x in w):
            add("cold_out_of_band", f"Outside the safe band for {n}+ min")
        n = rules["cold_door_open"]["duration_min"]
        w = last(n)
        if w and all(x["door_open"] for x in w):
            add("cold_door_open", f"Door open for {n}+ min")

    elif p["type"] == "water":
        if p["leak_wet"]:
            add("leak_probe_wet", "Leak probe is wet")
        r = rules["water_flow_high"]
        w = last(r["duration_min"])
        if w and all(x["flow_lpm"] > r["factor_over_normal"] * normal_flow for x in w):
            add("water_flow_high", f"Flow above {r['factor_over_normal']:g}x normal for {r['duration_min']} min")

    elif p["type"] == "thermostat":
        r = rules["hvac_vacant_running"]
        w = last(r["duration_min"])
        if w and all(x["hvac_on"] and not x["occupied"] and x["vacant_min"] >= r["vacant_min"]
                     and x["temp_c"] < x["setpoint_c"] - r["below_setpoint_c"] for x in w):
            add("hvac_vacant_running", "Still cooling an empty room below its setpoint")

    if p["battery_pct"] < rules["battery_low"]["battery_pct_below"]:
        add("battery_low", f"Battery at {p['battery_pct']:.0f} %")
    return found


def offline_finding(device_id, name, minutes_silent, rules):
    r = rules["sensor_silent"]
    return Finding(source=device_id, fault_type="sensor_offline", category="sensor_offline",
                   severity=r["severity"], method="rule", confidence=0.99,
                   title=TITLES["sensor_offline"].format(name=name),
                   detail=f"No data for {minutes_silent} min (expected every minute)", action=r["action"])
