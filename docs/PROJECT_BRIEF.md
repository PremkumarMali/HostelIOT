# MASTER PROMPT: Hotel IoT + AI Monitoring System

You are helping me build a final-year / demo project called **hotel-iot-ai**. Read this whole brief before writing any code. Work phase by phase (see "Build order"), and at the end of each phase stop, summarise what you built, tell me how to run it, and wait for me to say "next phase". If something in this brief is unclear or contradicts itself, ask me before guessing.

Save this brief into the repo as `docs/PROJECT_BRIEF.md` and keep a short `CLAUDE.md` at the root that points to it, so future sessions keep the context.

---

## 1. What I want to build

A smart-hotel monitoring system for **three IoT demos**, shown together on **one professional dashboard**, with an **AI layer** that detects faults and **automatically informs hotel management by SMS and WhatsApp**.

The three demos:

| # | Demo | Devices | Hotel area | Why it matters |
|---|------|---------|-----------|----------------|
| 1 | Smart room energy | Smart thermostat + occupancy sensor (+ PMS "sold" status) | Guest rooms | Strongest evidence of savings: occupancy-based HVAC control saves about 18–40% of HVAC energy |
| 2 | Water & leaks | Water flow meters + leak probes | Laundry, kitchen, guest floors, pool plant, boiler room | Fastest payback; shows event/alarm-driven IoT |
| 3 | Kitchen cold chain | Fridge/freezer temperature sensors + door sensors | Walk-in chiller, blast freezer, bar fridge, pastry fridge, minibar | Food safety (HACCP) compliance and audit logs |

Each demo has a different data style on purpose:
- Demo 1: **continuous** readings (every minute)
- Demo 2: **event-driven** (leak = alarm)
- Demo 3: **threshold / compliance** (must stay in a safe band)

Location context: the demo property is in **India** (Bengaluru), 20 rooms on 2 floors (101–110, 201–210). Currency ₹, use about ₹9/kWh for energy cost.

---

## 2. My tasks (requirements)

1. **One dashboard for all 3 demos**, everything detected and shown live.
2. The dashboard must **look professional**, like a real hotel operations console (not a student template).
3. **Use the IoT devices with the help of AI**: AI analyses the sensor streams.
4. When the AI detects an **error/fault**, it **informs management directly** via **SMS and WhatsApp APIs**.
5. For AI training, use the dataset strategy in section 6 (synthetic + real public datasets).
6. Use the file structure in section 9 exactly (you may add files, but tell me why).

---

## 3. Tech stack (decided)

- **Sensors:** Python simulator first (no hardware needed). Optional ESP32 + DHT22 + PIR firmware later.
- **Messaging:** MQTT via **Eclipse Mosquitto** (Docker).
- **Time-series DB:** **InfluxDB 3 Core** (or TimescaleDB if Influx is a problem; ask me first).
- **Backend:** **Python FastAPI** with REST + **WebSocket** for live push.
- **AI/ML:** Python, **scikit-learn** (Isolation Forest, Random Forest), pandas, joblib. Simple trend forecast first; LSTM optional later.
- **Notifications:** **WhatsApp Cloud API (Meta)** + **SMS** via **Twilio** (and keep an adapter for **MSG91** for India). Use a provider interface so they are swappable.
- **Frontend:** **React + Vite**, plain CSS with design tokens (light + dark theme). Hand-built SVG charts or a light chart lib (Recharts is fine).
- **Run everything with `docker-compose`.**
- Secrets only in `.env` (provide `.env.example`). Never hard-code keys or phone numbers.

---

## 4. Data model and MQTT

**Hierarchy:** Property → Floor/Zone → Room/Unit → Device → Metric.

**MQTT topic pattern:**
```
dt/hotel/{property}/{area}/{location}/{device_id}/{metric}
e.g. dt/hotel/blr01/floor2/207/thermo-207/telemetry
     dt/hotel/blr01/basement/laundry/water-laundry/telemetry
     dt/hotel/blr01/kitchen/walkin/cold-walkin/telemetry
```
Commands (later) use the `cmd/` prefix.

**Example payloads** (my design, adjust if needed):
```json
{"device_id":"thermo-207","type":"thermostat","room":"207","ts":"2026-10-24T22:30:00+05:30",
 "temp_c":23.4,"setpoint_c":22.5,"humidity_rh":51,"occupied":false,"vacant_min":16,
 "hvac_on":true,"pms_sold":true,"battery_pct":88}

{"device_id":"water-laundry","type":"water","zone":"laundry","ts":"...",
 "flow_lpm":21.3,"leak_wet":true,"battery_pct":92}

{"device_id":"cold-walkin","type":"cold_chain","unit":"walkin","ts":"...",
 "temp_c":6.1,"door_open":false,"safe_min_c":0,"safe_max_c":5,"battery_pct":77}
```
Validate all payloads with Pydantic schemas (`ingestion/schemas.py`).

**Sensor units & safe bands** (put in `config/devices.yaml`):
- Walk-in chiller 0–5 °C, blast freezer −22 to −18 °C, bar fridge 1–5 °C, pastry fridge 0–5 °C, minibar 2–8 °C.
- Water zones with normal flow: laundry 9, kitchen 6, guest floors 11, pool plant 4, boiler room 1.5 L/min.
- HVAC: ~1.1 kW per room when cooling; setback after 10 min vacant.

---

## 5. AI design (my idea + suggestions)

Three detection layers, run every minute by `ai_engine/detector.py`:

| Layer | Method | Catches |
|---|---|---|
| 1. Rules | Fixed limits from `config/alert_rules.yaml` | Fridge outside safe band for 3+ min, leak probe wet, sensor silent 3+ min |
| 2. Anomaly detection | **Isolation Forest**, one model per demo, on features (value, rolling mean/std, z-score, hour of day, occupancy) | Unusual water flow, AC on in empty room, abnormal energy |
| 3. Forecast | Linear trend first (slope over last 8 readings), LSTM optional | "Fridge will breach safe band in ~N min", i.e. warn **before** it happens |

Plus a **fault classifier** (Random Forest) trained on labelled synthetic faults to name the fault type: `leak`, `compressor_failure`, `door_left_open`, `hvac_stuck_on`, `sensor_offline`.

Every alert must include: id, title, detail, severity (`warning` / `critical`), confidence score (0–1), detection method, suggested action, source device, timestamp, status (`open` / `acknowledged` / `resolved`).

`ai_engine/alert_manager.py` must:
- **Deduplicate** (one open alert per source + fault type)
- **Escalate**: a critical alert not acknowledged in 10 min → SMS to General Manager
- Handle **acknowledge** from the dashboard or a WhatsApp "ACK" reply

Fault types I want to demo (also in the simulator's fault injector):
1. Water leak in a zone
2. Chiller compressor failure (temperature drifts up)
3. AC running in an empty room (HVAC stuck on)
4. Sensor offline (no heartbeat)

---

## 6. Dataset strategy (for AI training)

Use **both synthetic and real data**. No public dataset has labelled *hotel* faults, so faults must be generated.

- **Synthetic (main training set):** `ml/generate_synthetic.py` produces weeks of realistic normal data (daily patterns, occupancy cycles, door openings, noise) and **injects labelled faults**. Output CSV/Parquet to `ml/data/synthetic/` with a `label` column.
- **Real public datasets** (download into `ml/data/raw/`, used to make "normal" realistic and to validate):
  - **UCI Occupancy Detection**: real room temp, humidity, light, CO2 + occupancy labels (best fit for Demo 1)
  - **ASHRAE Great Energy Predictor III (Kaggle)**: building energy meter data
  - **LBNL HVAC Fault Detection & Diagnostics datasets**: HVAC data with labelled faults
  - **Numenta Anomaly Benchmark (NAB)**: includes a real machine-temperature failure series, for testing the anomaly model
- **Water leaks:** public leak datasets (LeakDB, BattLeDIM) are city pipe networks, so use mainly synthetic data for Demo 2.
- **Later:** add real readings from my own ESP32 sensors.

`ml/evaluate.py` must report precision, recall, F1, false alarms per day, and detection delay (minutes) for each fault type. Write a short `ml/README.md` explaining results.

If any dataset link or licence can't be verified, tell me instead of inventing it.

---

## 7. Notifications to management

- Provider interface in `notifier/base.py`; implementations `notifier/sms.py` (Twilio + MSG91) and `notifier/whatsapp.py` (WhatsApp Cloud API).
- Message templates in `notifier/templates.py`, e.g.
  `[CRITICAL] Water leak: Laundry. Flow 21.3 L/min vs normal 9.0. Action: isolate the zone valve. Reply ACK to acknowledge.`
- **Routing** (in `config/contacts.yaml`):
  - Water leak → Chief Engineer (WhatsApp + SMS), General Manager (SMS if critical)
  - Cold chain → Executive Chef (WhatsApp), Chief Engineer (SMS)
  - Room energy → Duty Manager (WhatsApp), Chief Engineer (WhatsApp)
  - Sensor offline → IT Manager (WhatsApp), Executive Chef (WhatsApp)
  - Escalation → General Manager (SMS)
- `notifier/webhook.py`: receives WhatsApp replies; "ACK" acknowledges the alert.
- **DRY_RUN mode (default ON):** log messages instead of sending, so the demo works without API keys. Only send real messages when `NOTIFY_DRY_RUN=false` and keys are set.
- Rate-limit: max 1 message per alert per recipient, plus escalation.
- India notes to document in README: business SMS needs **TRAI DLT registration** (sender ID + templates); WhatsApp business-initiated messages need **Meta-approved templates**.
- Log every message with status (queued → sent → delivered/failed) so the dashboard can show it.

---

## 8. Dashboard design (professional look)

I already have a working HTML prototype of the layout (I'll paste or add it as `docs/prototype/index.html` if you need it). Rebuild it in React with this layout:

- **Header:** property name, live status pill ("Live · AI monitoring"), clock, number of sensor streams.
- **Fault simulator bar** (demo mode only): buttons for Water leak, Chiller failure, AC on in empty room, Sensor offline, Pause.
- **KPI strip (6 tiles):** Rooms sold / guests in room, Energy saved (kWh + ₹), Water used (L), Cold-chain compliance (%), Open alerts (critical count), Messages sent.
- **Demo 1 panel:** floor map grid (rooms coloured: guest in room / sold but out / unsold / AC wasting energy / fault) + room detail (temp, setpoint, humidity, vacant time, HVAC energy, 60-min temperature chart).
- **Demo 2 panel:** total flow chart (last 60 min, L/min, axis labels) + zone list (current flow, normal flow, Dry/Leak pill).
- **Demo 3 panel:** each unit with current temp, safe band, sparkline with the safe band shaded, status pill (OK / At risk / Breach / Door open / Offline).
- **Right rail:** AI fault detection feed (severity stripe, confidence bar, suggested action, method, Acknowledge button) + Management notifications log (WA/SMS badge, recipient, masked number, status ticks).
- Style: clean operations-console look, blue-teal accent, semantic colours (green ok / amber warning / red critical), monospace font for numbers, **light and dark themes**, responsive down to phone width.
- Live updates via WebSocket, no page reloads.

---

## 9. File structure (use this)

```
hotel-iot-ai/
├── README.md
├── CLAUDE.md
├── docker-compose.yml              # Mosquitto, InfluxDB, backend, frontend
├── .env.example                    # API keys: Twilio / WhatsApp / MSG91
├── docs/
│   └── PROJECT_BRIEF.md            # this prompt
├── config/
│   ├── devices.yaml                # rooms, water zones, fridges, safe ranges
│   ├── alert_rules.yaml            # thresholds, severity, escalation time
│   └── contacts.yaml               # manager roles, phone numbers, channels
├── mosquitto/
│   └── mosquitto.conf
├── simulator/                      # fake sensors publishing over MQTT
│   ├── main.py
│   ├── room_sensor.py              # temp, humidity, occupancy, HVAC state
│   ├── water_sensor.py             # flow L/min, leak probe
│   ├── cold_chain_sensor.py        # fridge temp, door open/close
│   ├── fault_injector.py           # leak, compressor, stuck AC, offline
│   └── requirements.txt
├── firmware/                       # optional real hardware
│   └── esp32_room_node/
│       └── esp32_room_node.ino     # DHT22 + PIR → MQTT
├── ingestion/
│   ├── mqtt_consumer.py            # subscribes to dt/hotel/# topics
│   ├── schemas.py                  # payload validation
│   └── influx_writer.py            # writes to time-series DB
├── ml/
│   ├── data/
│   │   ├── raw/                    # UCI, ASHRAE, LBNL, NAB downloads
│   │   ├── synthetic/              # generated data with fault labels
│   │   └── processed/
│   ├── generate_synthetic.py
│   ├── features.py                 # rolling mean, z-score, hour of day
│   ├── train_anomaly.py            # Isolation Forest per demo
│   ├── train_fault_classifier.py   # Random Forest fault type
│   ├── forecast.py                 # predict fridge breach time
│   ├── evaluate.py                 # precision, recall, false alarms
│   ├── models/                     # saved .joblib models
│   └── notebooks/
│       └── 01_explore_data.ipynb
├── ai_engine/
│   ├── detector.py                 # runs rules + models every minute
│   ├── rules.py
│   ├── model_loader.py
│   └── alert_manager.py            # dedupe, escalation, acknowledge
├── notifier/
│   ├── base.py
│   ├── sms.py                      # Twilio or MSG91
│   ├── whatsapp.py                 # WhatsApp Cloud API
│   ├── templates.py                # approved message templates
│   └── webhook.py                  # receives "ACK" replies
├── backend/                        # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── websocket.py            # pushes live data to dashboard
│   │   └── api/
│   │       ├── rooms.py
│   │       ├── water.py
│   │       ├── cold_chain.py
│   │       └── alerts.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                       # React + Vite
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/Dashboard.jsx
│   │   ├── components/
│   │   │   ├── KpiStrip.jsx
│   │   │   ├── FloorMap.jsx
│   │   │   ├── RoomDetail.jsx
│   │   │   ├── WaterPanel.jsx
│   │   │   ├── ColdChainPanel.jsx
│   │   │   ├── AlertFeed.jsx
│   │   │   └── NotificationLog.jsx
│   │   ├── hooks/useLiveData.js
│   │   ├── api/client.js
│   │   └── styles/theme.css
│   └── package.json
└── tests/
    ├── test_rules.py
    ├── test_detector.py
    └── test_notifier.py
```

---

## 10. Build order (one phase at a time)

1. **Setup:** repo skeleton, `docker-compose.yml`, Mosquitto, InfluxDB, `.env.example`, config YAMLs, README with run steps.
2. **Simulator:** 20 rooms, 5 water zones, 5 cold units publishing every few seconds (1 tick = 1 simulated minute) + fault injector (CLI flags and an HTTP endpoint so the dashboard buttons can trigger faults).
3. **Ingestion:** MQTT consumer → schema validation → InfluxDB.
4. **Backend API + WebSocket:** current state, history (last 60 min), alerts, notifications, acknowledge, inject-fault endpoints.
5. **Dashboard (React):** full layout from section 8, wired to live data.
6. **ML:** synthetic generator, features, Isolation Forest + Random Forest + forecast, evaluation report.
7. **AI engine:** rules + models running every minute, alert manager with dedupe/escalation/ack.
8. **Notifier:** SMS + WhatsApp with DRY_RUN default, routing, webhook for ACK.
9. **Tests + polish:** pytest for rules/detector/notifier, README with screenshots, demo script ("press Water leak → alert in < 1 min → WhatsApp to Chief Engineer").

## 11. Rules for you while working

- Keep code simple and well commented; I need to explain it in a viva/demo.
- After each phase: list files created, how to run, how to test, and what's next.
- Don't add paid services or cloud accounts without asking.
- Never commit real phone numbers or API keys.
- Prefer working end-to-end over perfect; mark TODOs clearly.
- If a library version or API detail is uncertain, check the docs or tell me.

Start with **Phase 1** now.
