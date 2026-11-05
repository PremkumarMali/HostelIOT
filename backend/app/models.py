"""API data models: AI alerts and management notifications (brief §5 and §7)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Alert(BaseModel):
    id: str
    title: str                     # "Water leak: Laundry"
    detail: str                    # "Flow 21.3 L/min vs normal 9.0"
    severity: Literal["warning", "critical"]
    confidence: float = Field(ge=0, le=1)
    method: str                    # rule / anomaly / forecast / classifier
    fault_type: str                # leak / compressor_failure / door_left_open / hvac_stuck_on / sensor_offline
    category: str                  # water / cold_chain / room_energy / sensor_offline (routing key)
    action: str                    # suggested action for staff
    source: str                    # device_id
    section: str = ""              # dashboard section: "Guest rooms" / "Water & leaks" / "Kitchen cold chain"
    location: str = ""             # where exactly: "Room 207 · Floor 2", "Laundry · Basement"
    room: str | None = None        # room number when the fault is in a guest room
    ts: datetime
    status: Literal["open", "acknowledged", "resolved"] = "open"
    acked_by: str | None = None
    acked_at: datetime | None = None
    escalated: bool = False        # critical, not acknowledged in time -> General Manager informed
    updated_at: datetime | None = None
    resolved_at: datetime | None = None


class Notification(BaseModel):
    """A message to hotel management. Shown on the dashboard now; WhatsApp / SMS are on hold
    (same text, other channels later)."""
    id: str
    alert_id: str
    event: Literal["new", "upgraded", "escalated", "acknowledged", "resolved"]
    severity: Literal["critical", "warning", "info", "resolved"]
    channel: Literal["dashboard", "whatsapp", "sms"] = "dashboard"
    recipients: list[str]          # roles who should act, e.g. ["Chief Engineer", "General Manager"]
    section: str                   # "Water & leaks"
    location: str                  # "Laundry · Basement"
    room: str | None = None
    device_id: str
    title: str                     # "Water leak: Laundry"
    text: str                      # full message (same text a WhatsApp would carry)
    status: Literal["queued", "sent", "delivered", "failed"] = "delivered"
    ts: datetime
