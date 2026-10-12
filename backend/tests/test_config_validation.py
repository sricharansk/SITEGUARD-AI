"""Startup configuration validation for shared environments (ported from PR #2, Playbook Prompt 47)."""

import pytest

from app.core.config import Settings
from app.main import settings_problems, validate_settings

STRONG_SECRET = "Vq3-T8pZ_x1LmN4rW7yB2cD5eF6gH9jK0sA"  # test value only, never deployed


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)  # ignore any developer .env


def deployed(env: str = "staging", **kw) -> Settings:
    """Settings a staging or production deployment would use; each test breaks one of them."""
    values = {
        "env": env,
        "jwt_secret": STRONG_SECRET,
        "database_url": "postgresql+psycopg://siteguard@db.internal:5432/siteguard?sslmode=require",
        "cors_origins": "",
        "public_web_url": "https://siteguard.example.com/app",
        "seed_demo_data": False,
    }
    values.update(kw)
    return settings(**values)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_safe_deployed_settings_are_accepted(env):
    s = deployed(env)
    assert settings_problems(s) == []
    validate_settings(s)


def test_https_cors_origin_is_accepted():
    # The web app is served by the API (same origin), so CORS is usually empty; an https origin is fine too.
    assert settings_problems(deployed(cors_origins="https://siteguard.example.com")) == []


def test_host_names_containing_the_word_change_are_not_placeholders():
    assert settings_problems(deployed(public_web_url="https://exchange.example.com/app")) == []


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"jwt_secret": "dev-only-change-me"}, "at least 32 characters"),
        ({"jwt_secret": "short-but-random-Xy7"}, "at least 32 characters"),
        ({"jwt_secret": "CHANGE-to-a-long-random-string-for-staging"}, "placeholder"),
        ({"jwt_secret": "ab" * 20}, "too little variety"),
        ({"seed_demo_data": True}, "Demo data seeding"),
        ({"database_url": "sqlite:///./siteguard.db"}, "must point at PostgreSQL"),
        ({"database_url": "not a url"}, "must point at PostgreSQL"),
        ({"cors_origins": "*"}, "must not contain '*'"),
        ({"cors_origins": "https://siteguard.example.com, *"}, "must not contain '*'"),
        ({"cors_origins": "http://siteguard.example.com"}, "must use https://"),
        ({"public_web_url": "http://siteguard.example.com"}, "SITEGUARD_PUBLIC_WEB_URL must use https://"),
        (
            {"database_url": "postgresql+psycopg://siteguard:CHANGE-staging-db-password@db:5432/siteguard"},
            "SITEGUARD_DATABASE_URL still contains a template placeholder",
        ),
        ({"public_web_url": "https://CHANGE-staging-host.example.com"}, "still contains a template placeholder"),
    ],
)
def test_unsafe_deployed_settings_are_refused(env, override, fragment):
    s = deployed(env, **override)
    problems = settings_problems(s)
    assert any(fragment in p for p in problems), problems
    with pytest.raises(RuntimeError, match="Unsafe configuration"):
        validate_settings(s)


def test_staging_does_not_seed_demo_data_by_default():
    assert deployed(seed_demo_data=None).seed_demo_data is False


def test_every_problem_is_reported_at_once():
    s = deployed(
        "production",
        jwt_secret="x" * 40,
        seed_demo_data=True,
        database_url="sqlite:///./siteguard.db",
        cors_origins="*",
        public_web_url="http://siteguard.example.com",
    )
    assert len(settings_problems(s)) == 5


def test_unknown_environment_name_is_refused():
    with pytest.raises(RuntimeError, match="SITEGUARD_ENV must be one of"):
        validate_settings(settings(env="prod", jwt_secret=STRONG_SECRET))


@pytest.mark.parametrize("env", ["local", "test"])
def test_developer_environments_keep_their_defaults(env):
    # SQLite, http URLs, the default secret and demo seeding stay available on a developer machine.
    s = settings(env=env)
    assert settings_problems(s) == [] and s.seed_demo_data is True


def test_demo_environment_needs_a_real_secret_but_may_seed_and_use_http():
    assert settings_problems(settings(env="demo", jwt_secret=STRONG_SECRET)) == []
    default_secret = settings(env="demo", jwt_secret="dev-only-change-me")
    assert any("at least 32" in p for p in settings_problems(default_secret))


def test_smtp_is_refused_in_development_and_needs_starttls_when_deployed():
    dev = settings(env="test", notification_email_adapter="smtp")
    assert any("not allowed in local or test" in p for p in settings_problems(dev))
    assert settings_problems(settings(env="test", notification_email_adapter="log")) == []
    plain = deployed(notification_email_adapter="smtp", smtp_starttls=False, smtp_from="siteguard@example.com")
    assert any("SITEGUARD_SMTP_STARTTLS" in p for p in settings_problems(plain))
    placeholder = deployed(notification_email_adapter="smtp", smtp_from="siteguard@CHANGE-example.com")
    assert any("SITEGUARD_SMTP_FROM" in p for p in settings_problems(placeholder))
    assert settings_problems(deployed(notification_email_adapter="smtp", smtp_from="siteguard@example.com")) == []
