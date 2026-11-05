"""Fault injector: switch demo faults on/off, from the CLI or over HTTP.

HTTP API (used by the dashboard's fault buttons via the backend):
  GET  /status                                   -> sim time, paused, active faults
  POST /faults  {"type": "leak", "target": "laundry"}   (target optional)
  POST /clear   {"target": "laundry"}            (no target = clear everything)
  POST /pause   {"paused": true}                 (no body = toggle)
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

# Fault type -> default target used by the dashboard buttons
DEFAULT_TARGET = {
    "leak": "laundry",
    "compressor_failure": "walkin",
    "door_left_open": "pastry",
    "hvac_stuck_on": "207",
    "sensor_offline": "cold-bar",
}


class FaultInjector:
    def __init__(self, sensors):
        self.sensors = sensors
        self.paused = False
        self.sim_time = None

    def find(self, target):
        """A target is a room number, zone/unit id, or device id."""
        return next((s for s in self.sensors if target in (s.key, s.device_id)), None)

    def inject(self, fault, target=None):
        if fault not in DEFAULT_TARGET:
            raise ValueError(f"unknown fault type {fault!r}; use one of {list(DEFAULT_TARGET)}")
        sensor = self.find(str(target or DEFAULT_TARGET[fault]))
        if sensor is None:
            raise ValueError(f"unknown target {target!r}")
        if fault == "sensor_offline":
            sensor.offline = True                # any device can go silent
        elif fault in sensor.FAULTS:
            sensor.fault = fault
        else:
            raise ValueError(f"{fault} does not apply to {sensor.device_id}")
        return sensor.device_id

    def clear(self, target=None):
        for s in self.sensors:
            if target is None or str(target) in (s.key, s.device_id):
                s.fault, s.offline = None, False

    def active(self):
        out = [{"device_id": s.device_id, "fault": s.fault} for s in self.sensors if s.fault]
        out += [{"device_id": s.device_id, "fault": "sensor_offline"} for s in self.sensors if s.offline]
        return out

    def status(self):
        return {
            "sim_time": self.sim_time.isoformat(timespec="seconds") if self.sim_time else None,
            "paused": self.paused,
            "faults": self.active(),
        }


def serve(injector, host, port):
    """Run the HTTP API in a background thread."""

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/status":
                self.send_json(200, injector.status())
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                if self.path == "/faults":
                    device = injector.inject(body.get("type"), body.get("target"))
                    print(f"[fault] {body.get('type')} -> {device}")
                elif self.path == "/clear":
                    injector.clear(body.get("target"))
                    print(f"[fault] cleared {body.get('target') or 'all'}")
                elif self.path == "/pause":
                    injector.paused = bool(body.get("paused", not injector.paused))
                else:
                    return self.send_json(404, {"error": "not found"})
            except ValueError as e:              # also catches bad JSON
                return self.send_json(400, {"error": str(e)})
            self.send_json(200, injector.status())

        def log_message(self, *args):
            pass                                 # keep the console readable

    server = ThreadingHTTPServer((host, port), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
