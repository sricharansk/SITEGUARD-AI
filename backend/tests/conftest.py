import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="siteguard-test-"))
os.environ["SITEGUARD_DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["SITEGUARD_EVIDENCE_DIR"] = str(_tmp / "evidence")
os.environ["SITEGUARD_AI_PROVIDER"] = "rules"
os.environ["SITEGUARD_JWT_SECRET"] = "test-secret-not-for-production-use-0123456789"
os.environ.setdefault("SITEGUARD_DEMO_PASSWORD", "siteguard-demo")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = os.environ["SITEGUARD_DEMO_PASSWORD"]


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


_tokens: dict[str, str] = {}


def auth(client: TestClient, who: str) -> dict:
    if who not in _tokens:
        r = client.post("/auth/login", json={"email": f"{who}@demo.siteguard.local", "password": PASSWORD})
        assert r.status_code == 200, r.text
        _tokens[who] = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {_tokens[who]}"}


@pytest.fixture(scope="session")
def project_id(client) -> str:
    r = client.get("/projects", headers=auth(client, "hse"))
    return next(p["id"] for p in r.json()["data"] if p["code"] == "RMT-01")


@pytest.fixture(scope="session")
def org_id(client, project_id) -> str:
    return client.get(f"/projects/{project_id}", headers=auth(client, "hse")).json()["data"]["organization_id"]


@pytest.fixture
def db(client):
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        yield session
