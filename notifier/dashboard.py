"""Dashboard notification channel (WhatsApp / SMS are on hold).

Listens to the alert manager and turns each important alert event into a Notification
shown on every open dashboard: which section, which room / unit, what to do, and which
manager roles should act (routing from config/contacts.yaml, like the brief's §7).

  new / upgraded  -> roles routed for the alert's category (GM only when critical, if configured)
  escalated       -> escalation roles (General Manager)
  acknowledged    -> same roles as the alert ("stop, someone is on it")
  resolved        -> same roles as the alert
  updated         -> nothing (the alert card already shows the latest reading)
"""
from pathlib import Path

import yaml

from backend.app.models import Notification
from notifier.templates import render

CONTACTS = Path(__file__).resolve().parent.parent / "config" / "contacts.yaml"
NOTIFY_EVENTS = {"new", "upgraded", "escalated", "acknowledged", "resolved"}


class DashboardNotifier:
    def __init__(self, store, send, escalation_min=10, contacts_path=CONTACTS):
        """store: live store (keeps the log); send(msg): pushes a message to the dashboards."""
        with open(contacts_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.names = {key: c["name"] for key, c in cfg["contacts"].items()}
        self.routing = cfg["routing"]
        self.store, self.send, self.escalation_min = store, send, escalation_min
        self.counter = 0

    def recipients(self, category, severity):
        roles = []
        for r in self.routing.get(category, []):
            if r.get("only_if_severity") in (None, severity):
                roles.append(self.names[r["contact"]])
        return roles

    def __call__(self, event, alert):
        """Alert manager listener."""
        if event not in NOTIFY_EVENTS:
            return
        severity, title, text = render(event, alert, self.escalation_min)
        category = "escalation" if event == "escalated" else alert.category
        self.counter += 1
        n = Notification(id=f"N{self.counter:04d}", alert_id=alert.id, event=event, severity=severity,
                         recipients=self.recipients(category, alert.severity), section=alert.section,
                         location=alert.location, room=alert.room, device_id=alert.source, title=title,
                         text=text, ts=self.store.sim_now or alert.ts)   # events happen "now" (hotel time)
        self.store.add_notification(n)
        self.send({"type": "notification", "data": n.model_dump(mode="json")})
