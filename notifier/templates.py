"""Message text for every alert event.

The same text is shown on the dashboard today and can be sent unchanged over WhatsApp / SMS
later (those channels are on hold). Example:
  [CRITICAL] Water leak: Laundry
  Where: Water & leaks · Laundry · Basement
  Leak probe is wet. Flow 21.3 L/min vs normal 9.0, leak probe WET
  Action: Isolate the zone valve and send maintenance.
"""

SEVERITY = {  # event -> (notification severity, label) ; None = use the alert's own severity
    "new": (None, None),
    "upgraded": ("critical", "NOW CRITICAL"),
    "escalated": ("critical", "ESCALATED"),
    "acknowledged": ("info", "ACKNOWLEDGED"),
    "resolved": ("resolved", "RESOLVED"),
}


def render(event, alert, escalation_min=10):
    """(severity, title, text) for one alert event."""
    severity, label = SEVERITY[event]
    severity = severity or alert.severity
    label = label or alert.severity.upper()
    where = f"Where: {alert.section} · {alert.location}"

    if event == "escalated":
        body = (f"Not acknowledged for {escalation_min} min, General Manager informed. {alert.detail}\n"
                f"Action: {alert.action}")
    elif event == "acknowledged":
        body = f"Acknowledged by {alert.acked_by}. Escalation stopped."
    elif event == "resolved":
        body = "Readings are back to normal; the alert closed itself."
    else:
        body = f"{alert.detail}\nAction: {alert.action}"
    return severity, alert.title, f"[{label}] {alert.title}\n{where}\n{body}"
