# One Python image for the backend (API + ingestion) and the simulator.
# Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config config
COPY ingestion ingestion
COPY simulator simulator
COPY backend backend

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
