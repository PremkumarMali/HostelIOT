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
- [ ] Phase 7 — AI engine (wait for user go-ahead). Use ml/features.build_features + ml/forecast.forecast live;
      RF names faults, IF = warning-level safety net, heartbeat rule for offline.

Notes:
- Python venv at `.venv`; run tests with `.\.venv\Scripts\python -m pytest tests`. Run Python modules from the repo root (`ingestion`, `backend.app` are imported as packages; simulator uses flat imports).
- Store endpoints must be `async def` (store is only touched on the asyncio thread).
- Docker works (verified live 2026-10-26): `docker compose up -d --build` runs mosquitto, influxdb, backend, simulator end to end.
- `.env` files: comments must be on their own line (Docker treats `KEY=  # note` as the value).
