"""Write validated readings to InfluxDB 3 Core over its HTTP API (stdlib only).

Each reading becomes one line of InfluxDB "line protocol":
  table,tag=value,... field=value,... timestamp
  room,device_id=thermo-207,location=207,area=floor2 temp_c=23.4,occupied=f,vacant_min=16i 1793030400

Lines are buffered and sent in one POST per second (fewer HTTP calls).
The database and tables are created by InfluxDB on the first write.
"""
import os
import threading
import time
import urllib.error
import urllib.request

from ingestion.schemas import LOCATION_FIELD, TABLE

SKIP = {"type", "ts", "device_id"}    # stored as table / timestamp / tag, not as fields


def escape(text):
    """Escape commas, spaces and '=' in table names and tag values."""
    return str(text).replace(",", r"\,").replace(" ", r"\ ").replace("=", r"\=")


def field_value(v):
    if isinstance(v, bool):           # check bool first: bool is a subclass of int
        return "t" if v else "f"
    if isinstance(v, int):
        return f"{v}i"
    return repr(float(v))


def to_line(reading, area):
    data = reading.model_dump()
    loc_field = LOCATION_FIELD[reading.type]
    tags = {"device_id": reading.device_id, "location": data[loc_field], "area": area}
    fields = {k: v for k, v in data.items() if k not in SKIP and k != loc_field}
    tag_str = ",".join(f"{k}={escape(v)}" for k, v in tags.items())
    field_str = ",".join(f"{k}={field_value(v)}" for k, v in fields.items())
    return f"{TABLE[reading.type]},{tag_str} {field_str} {int(reading.ts.timestamp())}"


class InfluxWriter:
    def __init__(self, host=None, database=None, token=None, flush_s=1.0):
        host = host or os.getenv("INFLUX_HOST", "http://localhost:8181")
        database = database or os.getenv("INFLUX_DATABASE", "hotel")
        self.url = f"{host}/api/v3/write_lp?db={database}&precision=second"
        self.token = token if token is not None else os.getenv("INFLUX_TOKEN", "")
        self.buffer = []
        self.lock = threading.Lock()
        self.written = 0
        threading.Thread(target=self._flush_loop, args=(flush_s,), daemon=True).start()

    def write(self, reading, area):
        with self.lock:
            self.buffer.append(to_line(reading, area))

    def flush(self):
        with self.lock:
            lines, self.buffer = self.buffer, []
        if not lines:
            return
        req = urllib.request.Request(self.url, data="\n".join(lines).encode(), method="POST")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.written += len(lines)
        except urllib.error.HTTPError as e:   # 400 = bad line / type conflict; tell us which
            print(f"[influx] {e.code}: {e.read().decode(errors='replace')[:300]}")
        except OSError as e:
            # ponytail: drops this batch while Influx is down; add a retry queue if data loss matters
            print(f"[influx] unreachable ({e}); dropped {len(lines)} lines")

    def _flush_loop(self, flush_s):
        while True:
            time.sleep(flush_s)
            self.flush()
