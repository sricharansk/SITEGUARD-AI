import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, capa, dashboard, incidents, knowledge, projects
from app.core import db as dbmod
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.observability import CorrelationMiddleware, SecurityHeadersMiddleware, configure_logging

TITLE = "Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System"


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)
    from app.seed import seed_if_empty
    from app.services.embeddings import index_pending

    dbmod.run_migrations()
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


def validate_settings(s: Settings) -> None:
    """Refuse to start with settings that are unsafe outside a developer machine."""
    if s.env not in ("local", "test") and (s.jwt_secret == "dev-only-change-me" or len(s.jwt_secret) < 32):
        raise RuntimeError("Set SITEGUARD_JWT_SECRET to a random value of at least 32 characters")
    if s.is_production and s.seed_demo_data:
        raise RuntimeError("Demo data seeding is not allowed when SITEGUARD_ENV=production")


def create_app() -> FastAPI:
    s = get_settings()
    validate_settings(s)
    app = FastAPI(
        title=TITLE,
        version="0.1.0",
        description="Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform. "
        "AI output is decision support; humans approve every action.",
        lifespan=lifespan,
    )
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
    for r in (auth, projects, incidents, knowledge, agents, capa, dashboard):
        app.include_router(r.router)

    @app.get("/health", tags=["ops"])
    def health():
        return {"data": {"status": "ok", "ai_provider": s.ai_provider, "env": s.env}, "error": None}

    return app


app = create_app()
