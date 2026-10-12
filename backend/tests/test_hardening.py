from app.core.hardening import login_throttle
from tests.conftest import PASSWORD


def test_failed_logins_are_throttled_per_account_and_client(client):
    login_throttle.reset()
    body = {"email": "nobody-throttle@demo.siteguard.local", "password": "wrong"}
    codes = [client.post("/auth/login", json=body).status_code for _ in range(5)]
    assert codes == [401] * 5
    r = client.post("/auth/login", json=body)
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0
    # Another account from the same client is unaffected.
    ok = client.post("/auth/login", json={"email": "auditor@demo.siteguard.local", "password": PASSWORD})
    assert ok.status_code == 200
    login_throttle.reset()


def test_success_clears_failures_for_that_client(client):
    login_throttle.reset()
    for _ in range(4):
        client.post("/auth/login", json={"email": "qa@demo.siteguard.local", "password": "wrong"})
    assert (
        client.post("/auth/login", json={"email": "qa@demo.siteguard.local", "password": PASSWORD}).status_code == 200
    )
    for _ in range(4):
        assert (
            client.post("/auth/login", json={"email": "qa@demo.siteguard.local", "password": "wrong"}).status_code
            == 401
        )
    login_throttle.reset()


def test_security_headers(client):
    api = client.get("/health")
    assert api.headers["X-Content-Type-Options"] == "nosniff"
    assert api.headers["X-Frame-Options"] == "DENY"
    assert api.headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" not in api.headers  # Swagger UI at /docs needs its CDN
    assert "Strict-Transport-Security" not in api.headers  # local/test env only
    assert api.headers["Cache-Control"] == "no-store"
