import pytest
from fastapi.testclient import TestClient

from moiraflow_api.deps import get_agent_token_store, get_current_user, get_session
from moiraflow_api.main import app
from tests._helpers import make_sqlite_factory, seed_user, session_override


class FakeTokenStore:
    def __init__(self):
        self.issued = {}

    def issue(self, tenant_id, ttl_seconds=900):
        token = f"tok-{len(self.issued)}"
        self.issued[token] = tenant_id
        return token

    def consume(self, token):
        return self.issued.pop(token, None)


@pytest.fixture
def store():
    return FakeTokenStore()


def _client(store, role="admin"):
    factory = make_sqlite_factory()
    user = seed_user(factory, role=role)
    app.dependency_overrides[get_session] = session_override(factory)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_agent_token_store] = lambda: store
    return TestClient(app)


def test_full_enroll_register_approve_revoke(store):
    client = _client(store)
    try:
        token = client.post("/api/v1/agents/enroll").json()["enrollment_token"]
        reg = client.post(
            "/api/v1/agents/register",
            json={"token": token, "name": "edge-1", "public_key": "PUBKEY"},
        )
        assert reg.status_code == 200
        body = reg.json()
        assert body["status"] == "pending_approval"
        assert body["task_queue"] == f"agent-{body['agent_id']}"
        aid = body["agent_id"]

        listing = client.get("/api/v1/agents").json()
        assert listing[0]["name"] == "edge-1"

        approved = client.post(f"/api/v1/agents/{aid}/approve").json()
        assert approved["status"] == "approved"
        revoked = client.post(f"/api/v1/agents/{aid}/revoke").json()
        assert revoked["status"] == "revoked"
    finally:
        app.dependency_overrides.clear()


def test_register_with_invalid_token_401(store):
    client = _client(store)
    try:
        resp = client.post(
            "/api/v1/agents/register", json={"token": "nope", "name": "x", "public_key": "k"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_enrollment_token"
    finally:
        app.dependency_overrides.clear()


def test_token_is_single_use(store):
    client = _client(store)
    try:
        token = client.post("/api/v1/agents/enroll").json()["enrollment_token"]
        first = client.post(
            "/api/v1/agents/register", json={"token": token, "name": "a", "public_key": "k"}
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/agents/register", json={"token": token, "name": "b", "public_key": "k"}
        )
        assert second.status_code == 401  # token already consumed
    finally:
        app.dependency_overrides.clear()


def test_enroll_requires_admin(store):
    client = _client(store, role="developer")
    try:
        assert client.post("/api/v1/agents/enroll").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_register_with_csr_issues_certificate(store):
    from tests.test_ca import make_csr

    client = _client(store)
    try:
        token = client.post("/api/v1/agents/enroll").json()["enrollment_token"]
        reg = client.post(
            "/api/v1/agents/register",
            json={
                "token": token,
                "name": "edge-tls",
                "public_key": "PK",
                "csr": make_csr("edge-tls"),
            },
        ).json()
        assert reg["certificate"].startswith("-----BEGIN CERTIFICATE-----")
        assert reg["ca_certificate"].startswith("-----BEGIN CERTIFICATE-----")
        assert len(reg["fingerprint"]) == 64
        # the fingerprint is persisted on the agent row
        agent = client.get("/api/v1/agents").json()[0]
        assert agent["fingerprint"] == reg["fingerprint"]
    finally:
        app.dependency_overrides.clear()
