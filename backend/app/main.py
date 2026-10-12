import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.api import (
    agents,
    auth,
    capa,
    dashboard,
    graph,
    incidents,
    knowledge,
    notifications,
    projects,
    vision,
    workflows,
)
from app.core import db as dbmod
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.hardening import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.observability import CorrelationMiddleware, configure_logging
from app.services import graph as graph_service

TITLE = "Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System"


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)
    from app.seed import seed_if_empty
    from app.services.embeddings import index_pending

    if get_settings().auto_create_schema:
        dbmod.Base.metadata.create_all(dbmod.engine)
    with dbmod.SessionLocal() as session:
        if get_settings().seed_demo_data:
            seed_if_empty(session)
        # Chunks from before embeddings existed (or from a changed embedder) get vectors; idempotent.
        report = index_pending(session)
        session.commit()
        if report.embedded or report.failed:
            logging.getLogger("siteguard").info("startup embedding", extra={"extra_fields": report.__dict__})


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    yield
    graph_service.close_store()


KNOWN_ENVIRONMENTS = ("local", "test", "demo", "staging", "production")
NEO4J_SCHEMES = ("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://", "neo4j+ssc://")
NEO4J_TLS_SCHEMES = ("bolt+s://", "neo4j+s://")
# Shared environments that may hold real incident data: every check below applies (docs/SECURITY.md).
DEPLOYED_ENVIRONMENTS = ("staging", "production")
DEFAULT_JWT_SECRET = "dev-only-change-me"
# Template values contain this marker (.env.example, deployment/). Secrets are compared case-insensitively (which
# also catches the default secret); URLs only on the upper-case template form, since host names may contain the word.
PLACEHOLDER_MARKER = "CHANGE"
MIN_JWT_SECRET_LENGTH = 32
MIN_JWT_SECRET_DISTINCT_CHARS = 10


def settings_problems(s: Settings) -> list[str]:
    """Return every reason these settings are unsafe for `s.env`; empty when they are acceptable."""
    problems: list[str] = []
    if s.env not in KNOWN_ENVIRONMENTS:
        problems.append(f"SITEGUARD_ENV must be one of {', '.join(KNOWN_ENVIRONMENTS)} (got {s.env!r})")
    if s.env not in ("local", "test") and (
        s.jwt_secret == DEFAULT_JWT_SECRET or len(s.jwt_secret) < MIN_JWT_SECRET_LENGTH
    ):
        problems.append(f"Set SITEGUARD_JWT_SECRET to a random value of at least {MIN_JWT_SECRET_LENGTH} characters")
    if s.graph_backend == "neo4j":
        if not s.neo4j_uri.startswith(NEO4J_SCHEMES):
            problems.append("SITEGUARD_NEO4J_URI must use the bolt or neo4j scheme (bolt+s / neo4j+s for TLS)")
        if not s.neo4j_password.get_secret_value():
            problems.append("Set SITEGUARD_NEO4J_PASSWORD when SITEGUARD_GRAPH_BACKEND=neo4j")
    if s.env in ("local", "test") and s.notification_email_adapter == "smtp":
        problems.append("SITEGUARD_NOTIFICATION_EMAIL_ADAPTER=smtp is not allowed in local or test (use log)")
    if s.env in DEPLOYED_ENVIRONMENTS:
        problems += _deployed_problems(s)
    return problems


def _deployed_problems(s: Settings) -> list[str]:
    env = f"SITEGUARD_ENV={s.env}"
    problems: list[str] = []
    secret = s.jwt_secret
    if PLACEHOLDER_MARKER.lower() in secret.lower() or len(set(secret)) < MIN_JWT_SECRET_DISTINCT_CHARS:
        problems.append(
            "SITEGUARD_JWT_SECRET looks like a placeholder or has too little variety; generate one with "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"`'
        )
    if s.seed_demo_data:
        problems.append(f"Demo data seeding (known passwords) is not allowed when {env}")
    try:
        backend = make_url(s.database_url).get_backend_name()
    except ArgumentError:
        backend = "invalid"
    if backend != "postgresql":
        problems.append(f"SITEGUARD_DATABASE_URL must point at PostgreSQL when {env} (SQLite is for local runs)")
    origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
    if "*" in origins:
        problems.append(f"SITEGUARD_CORS_ORIGINS must not contain '*' when {env}")
    insecure = [o for o in origins if o != "*" and not o.startswith("https://")]
    if insecure:
        problems.append(f"SITEGUARD_CORS_ORIGINS must use https:// when {env} (got {', '.join(insecure)})")
    if not s.public_web_url.startswith("https://"):
        problems.append(f"SITEGUARD_PUBLIC_WEB_URL must use https:// when {env}")
    if s.graph_backend == "neo4j" and not s.neo4j_uri.startswith(NEO4J_TLS_SCHEMES):
        problems.append(f"SITEGUARD_NEO4J_URI must use verified TLS (bolt+s:// or neo4j+s://) when {env}")
    if s.notification_email_adapter == "smtp" and not s.smtp_starttls:
        problems.append(f"SITEGUARD_SMTP_STARTTLS must be true when {env} (credentials and incident details)")
    for name, value in (
        ("SITEGUARD_SMTP_FROM", s.smtp_from),
        ("SITEGUARD_DATABASE_URL", s.database_url),
        ("SITEGUARD_PUBLIC_WEB_URL", s.public_web_url),
        ("SITEGUARD_CORS_ORIGINS", s.cors_origins),
    ):
        if PLACEHOLDER_MARKER in value:
            problems.append(f"{name} still contains a template placeholder ({PLACEHOLDER_MARKER})")
    return problems


def validate_settings(s: Settings) -> None:
    """Refuse to start with settings that are unsafe for the configured environment."""
    problems = settings_problems(s)
    if problems:
        raise RuntimeError("Unsafe configuration: " + "; ".join(problems))


def create_app() -> FastAPI:
    s = get_settings()
    validate_settings(s)
    app = FastAPI(
        title=TITLE,
        version="0.2.0",
        description="Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform. "
        "AI output is decision support; humans approve every action.",
        lifespan=lifespan,
    )
    app.add_middleware(BodySizeLimitMiddleware)  # innermost: its 413 still gets headers and a correlation ID
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    install_error_handlers(app)
    routers = (auth, projects, incidents, knowledge, agents, capa, dashboard, notifications, vision, graph, workflows)
    for r in routers:
        app.include_router(r.router)

    if s.web_dir.is_dir():
        app.mount("/app", StaticFiles(directory=s.web_dir, html=True), name="web")

        @app.get("/", include_in_schema=False)
        def root():
            return RedirectResponse("/app/")

    @app.get("/health", tags=["ops"])
    def health():
        return {"data": {"status": "ok", "ai_provider": s.ai_provider, "env": s.env}, "error": None}

    return app


app = create_app()
