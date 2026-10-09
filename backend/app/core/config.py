from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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

    # Knowledge documents and retrieval (docs/AGENTS.md, docs/DATABASE.md).
    document_max_bytes: int = 25 * 1024 * 1024
    chunk_strategy: Literal["heading", "page", "semantic"] = "heading"
    chunk_max_chars: int = Field(default=900, ge=200, le=8000)
    embedding_provider: Literal["hashing"] = "hashing"
    retrieval_mode: Literal["hybrid", "lexical"] = "hybrid"
    # PDF and DOCX are parsed in a child process with these limits (hostile files must not stall the API).
    parser_timeout_seconds: int = Field(default=60, ge=5, le=600)
    parser_memory_mb: int = Field(default=1024, ge=256, le=8192)

    # Vision (docs/AGENTS.md#vision). "baseline" runs image-quality checks only; no detection model is chosen yet (O8).
    vision_provider: Literal["baseline", "anthropic"] = "baseline"
    vision_max_pixels: int = Field(default=40_000_000, ge=1_000_000, le=200_000_000)
    vision_max_side: int = Field(default=1568, ge=256, le=4096)
    vision_timeout_seconds: int = Field(default=30, ge=5, le=300)
    vision_memory_mb: int = Field(default=1024, ge=256, le=8192)
    vision_rate_limit_per_minute: int = Field(default=30, ge=1, le=1000)  # analyses per user

    # Notifications (docs/AGENTS.md#notifications). External delivery is off unless an adapter is chosen; "smtp" is
    # refused when SITEGUARD_ENV is local or test so development never emails real people.
    notification_email_adapter: Literal["disabled", "log", "smtp"] = "disabled"
    notification_max_attempts: int = Field(default=3, ge=1, le=10)
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "siteguard@localhost"
    smtp_starttls: bool = True
    public_web_url: str = "http://localhost:3000"
    escalation_overdue_days: int = Field(default=7, ge=1)
    escalation_unreviewed_hours: int = Field(default=24, ge=1)
    escalation_review_hours: int = Field(default=48, ge=1)

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
