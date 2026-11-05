# hotel-iot-ai

Smart-hotel IoT + AI monitoring demo for a 20-room property in Bengaluru:

1. **Smart room energy** — thermostats + occupancy (continuous data)
2. **Water & leaks** — flow meters + leak probes (event data)
3. **Kitchen cold chain** — fridge/freezer temps + door sensors (compliance data)

An AI layer (rules + Isolation Forest + trend forecast + Random Forest fault classifier) detects faults
and notifies management over WhatsApp and SMS. Full spec: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md).

```
simulator ──MQTT──▶ Mosquitto ──▶ ingestion ──▶ InfluxDB 3
                                       │
                                  ai_engine ──▶ notifier (WhatsApp / SMS)
                                       │
                            FastAPI + WebSocket ──▶ React dashboard
```

## Status

| Phase | What | State |
|---|---|---|
| 1 | Setup: compose, Mosquitto, InfluxDB, config | done |
| 2 | Simulator + fault injector | done |
| 3 | Ingestion → InfluxDB | done |
| 4 | Backend API + WebSocket | done |
| 5 | React dashboard | done |
| 6 | ML training + evaluation | done, see [ml/README.md](ml/README.md) |
| 7 | AI engine + alert manager | — |
| 8 | Notifier (WhatsApp / SMS) | — |
| 9 | Tests + polish | — |

## Requirements

- Docker Desktop (with `docker compose`)
- Python 3.11+ (simulator, ML) and Node 20+ (dashboard) — from later phases

## Run (Phase 1)

```powershell
copy .env.example .env        # defaults work as-is; NOTIFY_DRY_RUN=true
docker compose up -d
docker compose ps             # mosquitto + influxdb should be "running"
```

| Service | Port | Notes |
|---|---|---|
| Mosquitto (MQTT) | 1883 | anonymous, local demo only |
| InfluxDB 3 Core | 8181 | started with `--without-auth` for the demo |

### Smoke test

MQTT (two terminals):
```powershell
docker compose exec mosquitto mosquitto_sub -t "dt/hotel/#" -v
docker compose exec mosquitto mosquitto_pub -t "dt/hotel/blr01/kitchen/walkin/cold-walkin/telemetry" -m '{"temp_c":3.2}'
```

InfluxDB (the database is created on first write):
```powershell
curl.exe -X POST "http://localhost:8181/api/v3/write_lp?db=hotel" --data-binary "smoke,device=test value=1"
curl.exe "http://localhost:8181/api/v3/query_sql?db=hotel&q=SELECT+*+FROM+smoke"
```

Stop: `docker compose down` (add `-v` to wipe stored data).

## Run the simulator (Phase 2)

30 fake sensors (20 thermostats, 5 water meters, 5 fridges). 1 tick = 1 simulated minute, every 2 s by default.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r simulator\requirements.txt pytest

.\.venv\Scripts\python simulator\main.py                    # publish to Mosquitto
.\.venv\Scripts\python simulator\main.py --stdout --ticks 2 # no broker needed: print messages
.\.venv\Scripts\python simulator\main.py --fault leak:laundry --start 2026-10-24T22:00
.\.venv\Scripts\python -m pytest tests                      # simulator tests
```

| Fault (`--fault type[:target]`) | Default target | What happens |
|---|---|---|
| `leak` | `laundry` | flow +2x normal, leak probe wet after 2 min |
| `compressor_failure` | `walkin` | compressor stops, temp climbs ~0.1 °C/min out of band |
| `door_left_open` | `pastry` | door stays open, temp climbs |
| `hvac_stuck_on` | `207` | room empty but AC keeps running |
| `sensor_offline` | `cold-bar` | device stops publishing |

Fault API (while the simulator runs, bound to 127.0.0.1:8001):
```powershell
curl.exe localhost:8001/status
curl.exe -X POST localhost:8001/faults -d '{\"type\":\"leak\",\"target\":\"kitchen\"}'
curl.exe -X POST localhost:8001/clear  -d '{}'
curl.exe -X POST localhost:8001/pause  -d '{}'
```

## Run ingestion (Phase 3)

MQTT → Pydantic validation → InfluxDB. Needs `docker compose up -d` first.

```powershell
.\.venv\Scripts\pip install -r ingestion\requirements.txt
.\.venv\Scripts\python -m ingestion.mqtt_consumer      # terminal 1 (only when the backend is NOT running)
.\.venv\Scripts\python simulator\main.py               # terminal 2
```

The backend (Phase 4) runs this consumer itself, so normally you don't start it separately.

Every 10 s the consumer prints `messages ok=… rejected=… written_to_influx=…`. Check the data:

```powershell
curl.exe "http://localhost:8181/api/v3/query_sql?db=hotel&format=pretty&q=SELECT+time,location,temp_c,hvac_on+FROM+room+ORDER+BY+time+DESC+LIMIT+5"
curl.exe "http://localhost:8181/api/v3/query_sql?db=hotel&format=pretty&q=SELECT+location,count(*)+FROM+cold_chain+GROUP+BY+location"
```

| Influx table | Tags | Fields |
|---|---|---|
| `room` | device_id, location (room no.), area | temp_c, setpoint_c, humidity_rh, occupied, vacant_min, hvac_on, hvac_kw, pms_sold, battery_pct |
| `water` | device_id, location (zone), area | flow_lpm, leak_wet, battery_pct |
| `cold_chain` | device_id, location (unit), area | temp_c, door_open, safe_min_c, safe_max_c, battery_pct |

Timestamps are the **simulated** time from the payload, not the time of arrival.

## Run the backend (Phase 4)

Everything in Docker:
```powershell
docker compose up -d --build        # mosquitto, influxdb, backend (:8000), simulator
```

Or locally (with Mosquitto + InfluxDB from compose):
```powershell
.\.venv\Scripts\pip install -r backend\requirements.txt httpx
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload   # terminal 1
.\.venv\Scripts\python simulator\main.py                          # terminal 2
```

Interactive API docs: http://localhost:8000/docs

| Endpoint | What |
|---|---|
| `GET /api/snapshot` | everything the dashboard needs in one call |
| `GET /api/rooms` · `/api/rooms/{room}` · `/api/rooms/{room}/history` | Demo 1 |
| `GET /api/water` · `/api/water/history` | Demo 2 (total + per-zone flow, last 60 min) |
| `GET /api/cold-chain` · `/api/cold-chain/{unit}/history` | Demo 3 |
| `GET /api/alerts?status=open` · `POST /api/alerts/{id}/ack` | AI alerts (filled from Phase 7) |
| `GET /api/notifications` | WhatsApp / SMS log (filled from Phase 8) |
| `GET /api/sim/status` · `POST /api/sim/faults` · `/api/sim/clear` · `/api/sim/pause` | demo fault buttons (off when `DEMO_MODE=false`) |
| `WS /ws` | live push: `snapshot` on connect, then `reading`, `summary` (≤1/s), `alert`, `notification` |

```powershell
curl.exe -X POST localhost:8000/api/sim/faults -H "Content-Type: application/json" -d '{\"type\":\"leak\"}'
curl.exe localhost:8000/api/water
```

## Dashboard (Phase 5)

Everything in Docker: `docker compose up -d --build`, then open **http://localhost:8080**.

Live-editing the UI (backend still from compose or uvicorn on :8000):
```powershell
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api and /ws to :8000
```

Layout: header (live pill, hotel clock, stream count, theme toggle) → fault simulator (demo mode) → 6 KPI tiles →
Demo 1 floor map + room detail with 60-min temperature chart → Demo 2 total-flow chart + zone table →
Demo 3 cold units with safe-band sparklines → right rail: AI fault feed + management notification log.
Charts are hand-built SVG (`src/components/LineChart.jsx`, hover for exact values). Light/dark follows the OS;
the ☾/☀ button overrides it.

Statuses: rooms `guest_in / sold_out / unsold / wasting / fault / offline`, water `ok / high / leak / offline`,
cold `ok / at_risk / door_open / breach / offline` (`no_data` until the first reading).
Live state and the last 60 minutes are kept in memory; InfluxDB holds the full history.

## Configuration

| File | Purpose |
|---|---|
| `config/devices.yaml` | rooms, water zones, cold units, safe bands, HVAC parameters |
| `config/alert_rules.yaml` | rule thresholds, severities, forecast horizon, escalation time |
| `config/contacts.yaml` | manager roles and routing; phone numbers come from `.env` |
| `.env` | API keys and phone numbers (never committed) |

MQTT topics: `dt/hotel/{property}/{area}/{location}/{device_id}/{metric}`,
e.g. `dt/hotel/blr01/floor2/207/thermo-207/telemetry`.

## Datasets

Raw data is not committed. Recreate `ml/data/raw/` with:

```powershell
python ml/download_datasets.py           # UCI + NAB, ~4 MB
python ml/download_datasets.py --lbnl    # + LBNL fan-coil FDD, ~530 MB
```

| Dataset | Used for | Licence | Source |
|---|---|---|---|
| UCI Occupancy Detection (20,560 rows: temp, humidity, light, CO2, occupancy) | Demo 1 realistic room/occupancy patterns | CC BY 4.0 | [UCI #357](https://archive.ics.uci.edu/dataset/357/occupancy+detection) |
| NAB `machine_temperature_system_failure` + labelled anomaly windows | Testing the anomaly model and breach forecast on a real failure | MIT | [numenta/NAB](https://github.com/numenta/NAB) |
| LBNL FDD — fan coil unit (simulated, faulted + fault-free) | Demo 1 HVAC fault validation (hotel rooms usually run on FCUs) | CC BY 4.0 | [data.gov](https://catalog.data.gov/dataset/lbnl-fault-detection-and-diagnostics-datasets) · [faultdetection.lbl.gov](https://faultdetection.lbl.gov/) |
| ASHRAE Great Energy Predictor III | Building energy baselines (optional) | Kaggle competition rules | [Kaggle](https://www.kaggle.com/competitions/ashrae-energy-prediction/data) — needs a Kaggle account and accepting the rules; download manually into `ml/data/raw/ashrae/` |

Citation for LBNL: Granderson et al., "Building fault detection data to aid diagnostic algorithm creation and
performance testing", *Scientific Data* 7, 65 (2020).

Water leaks (Demo 2) and cold-chain faults use synthetic data (`ml/generate_synthetic.py`, Phase 6), because the
public leak datasets (LeakDB, BattLeDIM) model city pipe networks rather than buildings.

## Notifications in India

- **DRY_RUN is on by default** (`NOTIFY_DRY_RUN=true`): messages are logged, not sent.
- Business SMS in India requires **TRAI DLT registration** (entity, sender ID/header and each message template)
  before carriers deliver it — this applies to both Twilio and MSG91 traffic to Indian numbers.
- WhatsApp Cloud API: business-initiated messages (outside the 24-hour customer window) must use
  **Meta-approved message templates**. Free-form text works only as a reply within 24 h of the user's last message.
