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
    ts: datetime
    status: Literal["open", "acknowledged", "resolved"] = "open"
    acked_by: str | None = None
    acked_at: datetime | None = None


class Notification(BaseModel):
    id: str
    alert_id: str
    channel: Literal["whatsapp", "sms"]
    recipient: str                 # role, e.g. "Chief Engineer"
    to_masked: str                 # "+91 98xxxxxx21"; the full number never leaves the notifier
    text: str
    status: Literal["queued", "sent", "delivered", "failed"]
    ts: datetime
