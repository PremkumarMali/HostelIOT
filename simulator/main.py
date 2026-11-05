"""Hotel sensor simulator: 20 rooms, 5 water zones, 5 cold units -> MQTT.

1 tick = 1 simulated minute (default: one tick every 2 real seconds).

  python simulator/main.py                          # publish to Mosquitto
  python simulator/main.py --stdout --ticks 3       # print instead (no broker needed)
  python simulator/main.py --fault leak:laundry --fault compressor_failure
  python simulator/main.py --start 2026-10-24T22:00 --tick 1

Faults can also be switched over HTTP (see fault_injector.py), default port 8001.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from cold_chain_sensor import ColdChainSensor
from fault_injector import FaultInjector, serve
from room_sensor import RoomSensor
from water_sensor import WaterSensor

IST = timezone(timedelta(hours=5, minutes=30))   # India has no daylight saving
CONFIG = Path(__file__).resolve().parent.parent / "config" / "devices.yaml"


def load_config(path=CONFIG):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_sensors(cfg):
    prop = cfg["property"]["id"]
    sensors = [RoomSensor(room, floor, prop, cfg["rooms"]["hvac"])
               for floor, rooms in cfg["rooms"]["floors"].items() for room in rooms]
    sensors += [WaterSensor(zone, prop) for zone in cfg["water_zones"]]
    sensors += [ColdChainSensor(unit, prop) for unit in cfg["cold_units"]]
    return sensors


def mqtt_publisher():
    import paho.mqtt.client as mqtt  # imported here so --stdout works without paho

    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hotel-simulator")
    try:
        client.connect(host, port)
    except OSError as e:
        sys.exit(f"Cannot reach MQTT broker at {host}:{port} ({e}). Is `docker compose up -d` running?")
    client.loop_start()                          # background thread; reconnects automatically
    print(f"Publishing to mqtt://{host}:{port}")
    return lambda topic, payload: client.publish(topic, json.dumps(payload))


def parse_args():
    p = argparse.ArgumentParser(description="Hotel IoT sensor simulator")
    p.add_argument("--tick", type=float, default=2.0, help="real seconds per simulated minute")
    p.add_argument("--ticks", type=int, default=0, help="stop after N ticks (0 = run forever)")
    p.add_argument("--start", help="simulated start time, e.g. 2026-10-24T08:00 (default: now, IST)")
    p.add_argument("--fault", action="append", default=[],
                   help="type[:target], e.g. leak:laundry, hvac_stuck_on:207, sensor_offline:cold-bar")
    p.add_argument("--stdout", action="store_true", help="print messages instead of publishing")
    p.add_argument("--seed", type=int, help="random seed for a repeatable run")
    p.add_argument("--http-port", type=int, default=int(os.getenv("SIM_HTTP_PORT", "8001")))
    return p.parse_args()


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    sensors = build_sensors(load_config())
    injector = FaultInjector(sensors)
    for spec in args.fault:
        fault, _, target = spec.partition(":")
        print(f"[fault] {fault} -> {injector.inject(fault, target or None)}")

    if args.stdout:
        publish = lambda topic, payload: print(topic, json.dumps(payload))
    else:
        publish = mqtt_publisher()
        # 127.0.0.1 by default so nobody else on the network can inject faults
        host = os.getenv("SIM_HTTP_HOST", "127.0.0.1")
        serve(injector, host, args.http_port)
        print(f"Fault API on http://{host}:{args.http_port}/status")

    if args.start:
        sim_time = datetime.fromisoformat(args.start).replace(tzinfo=IST)
    else:
        sim_time = datetime.now(IST).replace(second=0, microsecond=0)
    print(f"{len(sensors)} sensors, 1 sim minute every {args.tick}s, starting {sim_time:%Y-%m-%d %H:%M}")

    tick = 0
    while not args.ticks or tick < args.ticks:
        if not injector.paused:
            tick += 1
            sim_time += timedelta(minutes=1)
            injector.sim_time = sim_time
            for s in sensors:
                payload = s.step(sim_time)           # offline sensors keep their state...
                if not s.offline:
                    publish(s.topic, payload)        # ...but send nothing
            if not args.stdout and tick % 10 == 0:
                faults = ", ".join(f"{f['fault']}@{f['device_id']}" for f in injector.active()) or "none"
                print(f"sim {sim_time:%H:%M}  tick {tick}  faults: {faults}")
        if args.ticks and tick >= args.ticks:
            break
        time.sleep(args.tick if not args.stdout else 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
