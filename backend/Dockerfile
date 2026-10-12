# Stage 1: build the web app (Next.js static export).
FROM node:22-slim AS web
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx next build

# Stage 2: API, which also serves the web app at /app.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/app ./app
COPY backend/migrations ./migrations
RUN pip install .
COPY data/seed /srv/data/seed
COPY data/eval /srv/data/eval
COPY --from=web /web/out /srv/web

RUN useradd --create-home --uid 10001 siteguard && mkdir -p /srv/evidence && chown siteguard /srv/evidence
USER siteguard
ENV SITEGUARD_SEED_DIR=/srv/data/seed SITEGUARD_EVIDENCE_DIR=/srv/evidence SITEGUARD_WEB_DIR=/srv/web \
    SITEGUARD_AUTO_CREATE_SCHEMA=false
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
# Apply database migrations, then start the API.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
