"""Generate labelled synthetic data by running the real simulator with scheduled faults.

No public dataset has labelled HOTEL faults, so we make our own: the same sensor models
that drive the live demo run for weeks of simulated time (1 row = 1 device-minute), and
faults are injected at random times on random devices. Each row gets a `label`.

  python ml/generate_synthetic.py          # train: 14 days (seed 1), test: 7 days (seed 2)

Output: ml/data/synthetic/{train,test}_{room,water,cold}.csv.gz with columns
  all payload fields + label (normal | fault type) + episode (id or -1)
  + fault_min (minutes since the fault started, -1 if none)
  + recovery (True for 30 min after a fault ends: the unit is still settling, so it is
    neither clearly "normal" nor still "faulty"; training skips it, evaluation forgives it)
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simulator"))
from cold_chain_sensor import ColdChainSensor  # noqa: E402
from main import IST, build_sensors, load_config  # noqa: E402
from room_sensor import RoomSensor  # noqa: E402
from water_sensor import WaterSensor  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "synthetic"
RECOVERY_MIN = 30

# fault type -> (sensor class it applies to, episodes per day, duration range in minutes)
FAULT_PLAN = {
    "hvac_stuck_on": (RoomSensor, 3, (30, 90)),
    "leak": (WaterSensor, 2, (20, 60)),
    "compressor_failure": (ColdChainSensor, 1, (40, 90)),
    "door_left_open": (ColdChainSensor, 2, (10, 30)),
    "sensor_offline": (object, 2, (5, 30)),          # any device
}
DEMO_OF = {RoomSensor: "room", WaterSensor: "water", ColdChainSensor: "cold"}


def plan_episodes(sensors, days):
    """Random, non-overlapping (per device) fault episodes: list of (start, end, fault, sensor)."""
    episodes, busy = [], {}                         # busy: device -> [(start, end incl. recovery)]
    for day in range(days):
        for fault, (cls, per_day, (lo, hi)) in FAULT_PLAN.items():
            placed = 0
            while placed < per_day:
                s = random.choice([x for x in sensors if isinstance(x, cls)])
                start = day * 1440 + random.randrange(1440)
                end = start + random.randint(lo, hi)
                slots = busy.setdefault(s.device_id, [])
                if any(start < b_end and end + RECOVERY_MIN > b_start for b_start, b_end in slots):
                    continue                        # overlaps another fault on this device: pick again
                slots.append((start, end + RECOVERY_MIN))
                episodes.append((start, end, fault, s))
                placed += 1
    return sorted(episodes, key=lambda e: e[0])


def generate(days, seed, name):
    random.seed(seed)
    sensors = build_sensors(load_config())
    episodes = plan_episodes(sensors, days)
    starts = {}
    ends = {}
    for i, (start, end, fault, s) in enumerate(episodes):
        starts.setdefault(start, []).append((i, fault, s))
        ends.setdefault(end, []).append((i, fault, s))

    active = {}                                     # device_id -> (episode id, fault)
    recovering = {}                                 # device_id -> minute when recovery ends
    rows = {"room": [], "water": [], "cold": []}
    t0 = datetime(2026, 9, 1, 0, 0, tzinfo=IST)

    for minute in range(days * 1440):
        for i, fault, s in ends.get(minute, []):    # end before start: back-to-back is allowed
            s.fault, s.offline = None, False
            active.pop(s.device_id, None)
            recovering[s.device_id] = minute + RECOVERY_MIN
        for i, fault, s in starts.get(minute, []):
            if fault == "sensor_offline":
                s.offline = True
            elif fault == "leak":
                s.fault = fault
                s.leak_extra = random.uniform(0.3, 2.0)   # drips to bursts; < 0.8x never wets the probe
            else:
                s.fault = fault
            active[s.device_id] = (i, fault)

        now = t0 + timedelta(minutes=minute)
        for s in sensors:
            p = s.step(now)
            if s.offline:
                continue                            # silent: no row, exactly like the live system
            ep, label = active.get(s.device_id, (-1, "normal"))
            fault_min = minute - episodes[ep][0] if ep >= 0 else -1      # minutes since this fault started
            p.update(label=label, episode=ep, fault_min=fault_min,
                     recovery=minute < recovering.get(s.device_id, -1))
            rows[DEMO_OF[type(s)]].append(p)

    OUT.mkdir(parents=True, exist_ok=True)
    for demo, data in rows.items():
        df = pd.DataFrame(data)
        df.to_csv(OUT / f"{name}_{demo}.csv.gz", index=False)
        counts = df["label"].value_counts().to_dict()
        print(f"{name}_{demo}: {len(df):,} rows  {counts}")

    ep = pd.DataFrame([{"episode": i, "start": t0 + timedelta(minutes=a), "end": t0 + timedelta(minutes=b),
                        "fault": f, "device_id": s.device_id, "demo": DEMO_OF.get(type(s))}
                       for i, (a, b, f, s) in enumerate(episodes)])
    ep.to_csv(OUT / f"{name}_episodes.csv", index=False)
    print(f"{name}: {len(ep)} fault episodes over {days} days")


if __name__ == "__main__":
    generate(days=14, seed=1, name="train")
    generate(days=7, seed=2, name="test")
