# One Python image for the backend (API + ingestion + AI engine) and the simulator.
# Build context is the repo root (see docker-compose.yml).
# Same Python as the .venv the models were trained in, so the saved models load cleanly.
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config config
COPY ingestion ingestion
COPY simulator simulator
COPY ml ml
COPY ai_engine ai_engine
COPY notifier notifier
COPY backend backend

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
