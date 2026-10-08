from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, auth, capa, dashboard, incidents, knowledge, projects
from app.core import db as dbmod
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.observability import CorrelationMiddleware, configure_logging

TITLE = "Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System"


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)
    from app.seed import seed_if_empty

    dbmod.Base.metadata.create_all(dbmod.engine)
    if get_settings().seed_demo_data:
        with dbmod.SessionLocal() as session:
            seed_if_empty(session)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    if s.env not in ("local", "test") and (s.jwt_secret == "dev-only-change-me" or len(s.jwt_secret) < 32):
        raise RuntimeError("Set SITEGUARD_JWT_SECRET to a random value of at least 32 characters")
    app = FastAPI(
        title=TITLE,
        version="0.1.0",
        description="Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform. "
        "AI output is decision support; humans approve every action.",
        lifespan=lifespan,
    )
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
