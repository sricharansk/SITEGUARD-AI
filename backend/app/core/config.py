from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SITEGUARD_", extra="ignore")

    env: str = "local"
    database_url: str = "sqlite:///./siteguard.db"
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_minutes: int = 480
    # Failed logins allowed per (email, client) and per email inside the window before HTTP 429.
    login_max_failures: int = 5
    login_max_failures_per_account: int = 20
    login_window_seconds: int = 900
    evidence_dir: Path = Path("./evidence_store")
    evidence_max_bytes: int = 10 * 1024 * 1024
    # Demo users share a known password, so seeding defaults to on only for local/test/demo environments.
    seed_demo_data: bool | None = None
    # create_all at startup for local runs and tests. Deployed images run `alembic upgrade head` and set this false.
    auto_create_schema: bool = True
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    cors_origins: str = "http://localhost:3000"
    # Built web app (frontend/out). Served at /app when the directory exists.
    web_dir: Path = REPO_ROOT / "frontend" / "out"
    # Public address of the web app (links in notifications; https required in staging and production).
    public_web_url: str = "http://localhost:8000/app"

    # AI provider: "rules" (deterministic, offline) or "anthropic".
    ai_provider: str = "rules"
    anthropic_model: str = "claude-opus-5-5"
    agent_timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _resolve_seed_default(self) -> "Settings":
        if self.seed_demo_data is None:
            self.seed_demo_data = self.env in ("local", "test", "demo")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
