# hotel-iot-ai

Smart-hotel IoT + AI monitoring demo (rooms energy, water/leaks, kitchen cold chain).
**Full spec: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) — read it before working.**

Working rules (from the brief):
- Build one phase at a time (brief §10); stop after each phase, summarise files / how to run / how to test / what's next, and wait for "next phase".
- Keep code simple and commented (it's explained in a viva).
- Secrets and phone numbers only in `.env` — never in code or committed files.
- Notifications default to `NOTIFY_DRY_RUN=true`.
- No paid services or cloud accounts without asking.

Progress:
- [x] Phase 1 — setup (compose, Mosquitto, InfluxDB 3 Core, config YAMLs)
- [x] Phase 2 — simulator (+ datasets in ml/data/raw via ml/download_datasets.py)
- [x] Phase 3 — ingestion (MQTT → schemas → Influx line protocol over HTTP)
- [x] Phase 4 — backend API + WebSocket (backend runs the ingestion consumer in-process; live store in memory)
- [x] Phase 5 — React dashboard (Vite + plain CSS tokens, hand-built SVG charts; served by nginx on :8080)
- [x] Phase 6 — ML (synthetic data from the simulator itself; IF + RF + trend forecast; results in ml/README.md)
- [x] Phase 7 — AI engine (backend/app/ai.py runs ai_engine every sim minute; alert manager dedupe/upgrade/escalate/resolve)
- [x] Phase 8 — notifications ON THE DASHBOARD (user decision 2026-11-05: WhatsApp/SMS on hold). notifier/dashboard.py +
      templates.py; each notification names section + room/unit + roles; toasts + feed + click-to-jump.
      To add WhatsApp/SMS later: another listener on backend.app.ai.manager.listeners reusing notifier/templates.render().
- [x] Phase 9 — tests + polish: README rewritten (quick start, screenshots in docs/screenshots), docs/DEMO_SCRIPT.md,
      pytest.ini, alert feed fixes, Isolation Forest alerts need 5 unusual minutes (anomaly.min_consecutive).

All brief phases done. WhatsApp/SMS remains on hold until the user asks (see README "Limits").

Notes:
- Python venv at `.venv`; run tests with `.\.venv\Scripts\python -m pytest` (~3 min; detector tests run the simulator). Run Python modules from the repo root (`ingestion`, `backend.app` are imported as packages; simulator uses flat imports).
- Store endpoints must be `async def` (store is only touched on the asyncio thread).
- Backend image = python:3.14-slim with scikit-learn==1.9.1 (must match the version models were trained with); it copies ml/ incl. ml/models.
- Docker works: `docker compose up -d --build` runs mosquitto, influxdb, backend, simulator, frontend (:8080). Config files are baked into the backend image: rebuild after editing config/.
- `.env` files: comments must be on their own line (Docker treats `KEY=  # note` as the value).
