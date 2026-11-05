"""Turns findings into alerts: deduplicate, upgrade, escalate, acknowledge, resolve.

  dedupe     one active alert per (device, fault type); later findings update it
  upgrade    a warning that turns critical (e.g. forecast -> actual breach) is upgraded in place
             and re-opened, so it needs a fresh acknowledgement
  escalate   critical + not acknowledged for 10 min -> "escalated" event (Phase 8 SMSes the GM)
  ack        from the dashboard or a WhatsApp "ACK" reply; stops escalation
  resolve    fault not seen for 5 min -> resolved automatically

All times are simulated hotel time. Other parts listen to events via `listeners`:
  fn(event, alert) with event in new | upgraded | updated | escalated | acknowledged | resolved
"""
from datetime import timedelta

from backend.app.models import Alert

METHOD_ORDER = ["rule", "classifier", "forecast", "anomaly"]   # most to least certain
SEVERITY_RANK = {"warning": 0, "critical": 1}


def _best(findings):
    """The finding that describes the alert best: most severe, then most certain method, then confidence."""
    return max(findings, key=lambda f: (SEVERITY_RANK[f.severity], -METHOD_ORDER.index(f.method), f.confidence))


class AlertManager:
    def __init__(self, store, escalation_min=10, resolve_after_min=5):
        self.store = store
        self.escalation = timedelta(minutes=escalation_min)
        self.resolve_after = timedelta(minutes=resolve_after_min)
        self.listeners = []
        self.active = {}          # (source, fault_type) -> alert id (open or acknowledged)
        self.last_seen = {}       # alert id -> last minute the fault was detected
        self.critical_since = {}  # alert id -> when it became critical
        self.counter = 0

    def emit(self, event, alert):
        self.store.dirty = True
        for fn in self.listeners:
            fn(event, alert)

    def process(self, findings, now):
        groups = {}
        for f in findings:
            groups.setdefault((f.source, f.fault_type), []).append(f)

        for key, fs in groups.items():
            best = _best(fs)
            methods = "+".join(sorted({f.method for f in fs}, key=METHOD_ORDER.index))
            aid = self.active.get(key)
            if aid is None:
                self._open(key, best, methods, now)
                continue
            alert = self.store.alerts[aid]
            self.last_seen[aid] = now
            upgraded = SEVERITY_RANK[best.severity] > SEVERITY_RANK[alert.severity]
            before = (alert.title, alert.detail, alert.method)
            alert.title, alert.detail, alert.action, alert.method = best.title, best.detail, best.action, methods
            alert.confidence = max(alert.confidence, best.confidence)
            alert.updated_at = now
            if upgraded:
                alert.severity, alert.status = "critical", "open"      # new danger: needs a fresh ack
                alert.acked_by = alert.acked_at = None
                self.critical_since[aid] = now
                self.emit("upgraded", alert)
            elif before != (alert.title, alert.detail, alert.method):
                self.emit("updated", alert)

        for key, aid in list(self.active.items()):
            alert = self.store.alerts[aid]
            if key not in groups and now - self.last_seen[aid] >= self.resolve_after:
                alert.status, alert.resolved_at = "resolved", now
                del self.active[key]
                self.emit("resolved", alert)
            elif (alert.status == "open" and alert.severity == "critical" and not alert.escalated
                  and now - self.critical_since[aid] >= self.escalation):
                alert.escalated = True
                self.emit("escalated", alert)

    def _open(self, key, f, methods, now):
        self.counter += 1
        section, location, room = self.store.locate(f.source)       # which section + which room / unit
        alert = Alert(id=f"A{self.counter:04d}", title=f.title, detail=f.detail, severity=f.severity,
                      confidence=f.confidence, method=methods, fault_type=f.fault_type, category=f.category,
                      action=f.action, source=f.source, section=section, location=location, room=room,
                      ts=now, updated_at=now)
        self.store.add_alert(alert)
        self.active[key] = alert.id
        self.last_seen[alert.id] = now
        if alert.severity == "critical":
            self.critical_since[alert.id] = now
        self.emit("new", alert)

    def acknowledge(self, alert_id, by, now):
        """Returns the alert (unchanged if it was not open), or None if unknown."""
        alert = self.store.alerts.get(alert_id)
        if alert and alert.status == "open":
            self.store.ack(alert_id, by, now)
            self.emit("acknowledged", alert)
        return alert
