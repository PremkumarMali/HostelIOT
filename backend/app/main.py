"""FastAPI backend: REST API + WebSocket for the dashboard.

Run from the repo root:
  uvicorn backend.app.main:app --reload

On startup it also runs the ingestion consumer (MQTT -> validate -> InfluxDB),
and every valid reading also updates the live store and is pushed over the WebSocket.
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import alerts, cold_chain, rooms, simulator, water
from backend.app.db import store
from backend.app.websocket import hub, router as ws_router, summary_loop
from ingestion import mqtt_consumer
from ingestion.influx_writer import InfluxWriter


def on_reading(payload):
    """Runs on the asyncio thread for every valid reading."""
    store.update(payload)
    kind, view = store.device_view(payload)
    if view:
        hub.send({"type": "reading", "kind": kind, "data": view})


@asynccontextmanager
async def lifespan(app):
    loop = asyncio.get_running_loop()
    writer = InfluxWriter()

    class Sink:
        """Where the MQTT thread delivers each valid reading."""
        def write(self, reading, area):
            writer.write(reading, area)
            # hand over to the asyncio thread, so the store is only touched there
            loop.call_soon_threadsafe(on_reading, reading.model_dump(mode="json"))

    client = None
    if os.getenv("MQTT_ENABLED", "true").lower() != "false":
        client = mqtt_consumer.start(Sink(), client_id="hotel-backend")
    task = asyncio.create_task(summary_loop())
    yield
    task.cancel()
    if client:
        client.loop_stop()
        client.disconnect()
    writer.flush()


app = FastAPI(title="Hotel IoT + AI monitoring", lifespan=lifespan)
for module in (rooms, water, cold_chain, alerts, simulator):
    app.include_router(module.router)
app.include_router(ws_router)


@app.get("/api/health")
async def health():
    return {"ok": True, "sim_time": store.summary()["sim_time"], "streams": len(store.latest)}


@app.get("/api/snapshot")
async def snapshot():
    return store.snapshot()
