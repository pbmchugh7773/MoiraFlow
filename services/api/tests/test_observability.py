from fastapi.testclient import TestClient

from moiraflow_api.deps import get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, session_override


def test_healthz_is_public_and_ok():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_checks_db():
    factory = make_sqlite_factory()
    app.dependency_overrides[get_session] = session_override(factory)
    try:
        resp = TestClient(app).get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
    finally:
        app.dependency_overrides.clear()


def test_metrics_exposes_request_counter():
    client = TestClient(app)
    client.get("/healthz")  # generate at least one request
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "moiraflow_http_requests_total" in resp.text
