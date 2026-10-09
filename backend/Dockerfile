# Site Guard AI API: production image. Non-root, health check, configuration only from the environment.
#
# Build (from the repository root): docker build -f backend/Dockerfile -t siteguard-api .
# Run: docker run -p 8000:8000 --env-file <env file> -v siteguard-evidence:/srv/evidence siteguard-api
#
# Nothing secret is copied in: backend/Dockerfile.dockerignore sends only the lock file, the app package and the
# synthetic seed data to the builder. SITEGUARD_ENV defaults to production, so a container started without
# configuration refuses to run until it gets a real JWT secret, PostgreSQL and https URLs (validate_settings in
# app/main.py). Local stacks set SITEGUARD_ENV=local or demo explicitly (docker-compose.yml, .env.example).
#
# Behind a TLS-inspecting proxy, pass its CA bundle as a build secret; it is mounted only while pip runs and is
# never written to a layer:  docker build --secret id=build_ca,src=/path/to/ca-bundle.pem ...

# Pinned by digest so rebuilds use the same base; bump the tag and digest together (docs/DEPLOYMENT.md).
ARG PYTHON_IMAGE=python:3.12.15-slim-trixie@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

FROM ${PYTHON_IMAGE} AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY backend/requirements.lock /tmp/requirements.lock
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    /opt/venv/bin/pip install -r /tmp/requirements.lock

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/srv/backend \
    SITEGUARD_ENV=production \
    SITEGUARD_SEED_DIR=/srv/data/seed \
    SITEGUARD_EVIDENCE_DIR=/srv/evidence
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin siteguard \
    && mkdir -p /srv/evidence \
    && chown siteguard:siteguard /srv/evidence
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv/backend
# Code and seed data stay root-owned (read-only for the app user); only /srv/evidence is writable.
COPY backend/alembic.ini ./
COPY backend/app ./app
COPY data/seed /srv/data/seed
USER siteguard
EXPOSE 8000
# Migrations run on startup (DECISIONS 011), so give the first health check time.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
