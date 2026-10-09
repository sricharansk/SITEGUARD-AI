FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

COPY backend/requirements.lock ./
RUN pip install -r requirements.lock
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/app ./app
RUN pip install --no-deps .
COPY data/seed /srv/data/seed

RUN useradd --create-home --uid 10001 siteguard && mkdir -p /srv/evidence && chown siteguard /srv/evidence
USER siteguard
ENV SITEGUARD_SEED_DIR=/srv/data/seed SITEGUARD_EVIDENCE_DIR=/srv/evidence
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
