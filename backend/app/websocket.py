"""WebSocket /ws: pushes live data to every open dashboard.

Messages (all JSON with a "type"):
  snapshot      once on connect: everything (summary, rooms, water, cold_chain, alerts, notifications)
  reading       one device changed:  {"type": "reading", "kind": "room"|"water"|"cold_chain", "data": {...}}
  summary       KPIs + offline list, at most once per second
  alert         an alert was raised / acknowledged / resolved
  notification  a WhatsApp / SMS message changed status
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.db import store

router = APIRouter()


class Hub:
    def __init__(self):
        self.clients = set()

    async def broadcast(self, msg):
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:                      # browser tab closed mid-send
                self.clients.discard(ws)

    def send(self, msg):
        """Fire-and-forget broadcast; call from the asyncio thread."""
        if self.clients:
            asyncio.get_running_loop().create_task(self.broadcast(msg))


hub = Hub()


@router.websocket("/ws")
async def live(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "snapshot", "data": store.snapshot()})
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()                # we only push; this just waits for disconnect
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


async def summary_loop():
    """Push the KPI summary at most once a second, only when something changed."""
    while True:
        await asyncio.sleep(1)
        if store.dirty:
            store.dirty = False
            hub.send({"type": "summary", "data": store.summary()})
