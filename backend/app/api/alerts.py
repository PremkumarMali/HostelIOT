"""AI alerts and the management notification log."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.ai import manager
from backend.app.db import store

router = APIRouter(prefix="/api", tags=["alerts"])


class AckRequest(BaseModel):
    by: str = Field(default="dashboard", max_length=64)


@router.get("/alerts")
async def list_alerts(status: Literal["open", "acknowledged", "resolved"] | None = None):
    alerts = [a for a in store.alerts.values() if status is None or a.status == status]
    return sorted(alerts, key=lambda a: a.ts, reverse=True)


@router.post("/alerts/{alert_id}/ack")
async def acknowledge(alert_id: str, body: AckRequest | None = None):
    # TODO (production): require a logged-in user; the demo dashboard has no auth
    # The alert manager records the ack, stops escalation and tells every dashboard.
    alert = manager.acknowledge(alert_id, (body or AckRequest()).by, store.sim_now or datetime.now().astimezone())
    if alert is None:
        raise HTTPException(404, "unknown alert")
    return alert


@router.get("/notifications")
async def list_notifications(limit: int = 50):
    return store.notifications[-limit:][::-1]       # newest first
