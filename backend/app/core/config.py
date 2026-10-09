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
    evidence_dir: Path = Path("./evidence_store")
    evidence_max_bytes: int = 10 * 1024 * 1024
    # Demo users share a known password, so seeding defaults to on only for local/test/demo environments.
    seed_demo_data: bool | None = None
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    cors_origins: str = "http://localhost:3000"

    # AI provider: "rules" (deterministic, offline) or "anthropic".
    ai_provider: str = "rules"
    anthropic_model: str = "claude-opus-5-5"
    agent_timeout_seconds: float = 60.0
    login_rate_limit_per_minute: int = 10

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
