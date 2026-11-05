"""MQTT -> validate -> InfluxDB.

Subscribes to dt/hotel/#, checks every message against the schemas and hands the
valid ones to a "sink" (anything with .write(reading, area)). Invalid messages are
logged and dropped.

  python -m ingestion.mqtt_consumer        (run from the repo root)

The backend runs this same consumer in-process (see backend/app/main.py), so only run
it standalone when the backend is NOT running, otherwise readings are written twice.
"""
import os
import time

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from ingestion.influx_writer import InfluxWriter
from ingestion.schemas import parse

TOPIC = "dt/hotel/#"
stats = {"ok": 0, "rejected": 0}


def handle(topic, raw, sink):
    """Validate one message; returns None if accepted, or the reason it was rejected."""
    # dt/hotel/{property}/{area}/{location}/{device_id}/{metric}
    parts = topic.split("/")
    if len(parts) != 7 or parts[6] != "telemetry":
        return f"unexpected topic {topic}"
    try:
        reading = parse(raw)
    except ValidationError as e:
        return f"invalid payload: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"
    if reading.device_id != parts[5]:
        return f"device_id {reading.device_id!r} does not match topic"
    sink.write(reading, area=parts[3])
    return None


def start(sink, client_id="hotel-ingestion"):
    """Connect to MQTT in a background thread; every valid reading goes to sink.write()."""

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"MQTT connected ({reason_code}); subscribing to {TOPIC}")
        client.subscribe(TOPIC)              # re-subscribes after every reconnect

    def on_message(client, userdata, msg):
        try:
            error = handle(msg.topic, msg.payload, sink)
        except Exception as e:               # never let one message kill the MQTT thread
            error = f"internal error: {e!r}"
        if error:
            stats["rejected"] += 1
            print(f"[rejected] {msg.topic}: {error}")
        else:
            stats["ok"] += 1

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    host, port = os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883"))
    print(f"Connecting to mqtt://{host}:{port}")
    client.connect_async(host, port)         # keeps retrying until the broker is up
    client.loop_start()
    return client


def main():
    writer = InfluxWriter()
    print(f"Writing to {writer.url}")
    start(writer)
    while True:
        time.sleep(10)
        print(f"messages ok={stats['ok']} rejected={stats['rejected']} written_to_influx={writer.written}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
