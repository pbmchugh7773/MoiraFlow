import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.agent_crypto import decrypt_for_agent
from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import agents as svc
from moiraflow_api.services import secrets as secrets_svc


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    t = models.Tenant(name="T", slug="default")
    session.add(t)
    session.flush()
    return t


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


def _agent(session, tenant, *, status, fingerprint, public_key=""):
    agent = models.Agent(
        tenant_id=tenant.id,
        name="a",
        status=status,
        os="linux",
        task_queue="agent-x",
        fingerprint=fingerprint,
        public_key=public_key,
    )
    session.add(agent)
    session.flush()
    return agent


def test_verify_authorizes_approved(session, tenant):
    _agent(session, tenant, status="approved", fingerprint="fp-ok")
    assert svc.verify_agent(session, "fp-ok").status == "approved"


def test_verify_denies_revoked(session, tenant):
    _agent(session, tenant, status="revoked", fingerprint="fp-rev")
    with pytest.raises(svc.AgentNotAuthorizedError):
        svc.verify_agent(session, "fp-rev")


def test_verify_denies_pending_and_unknown(session, tenant):
    _agent(session, tenant, status="pending_approval", fingerprint="fp-pend")
    with pytest.raises(svc.AgentNotAuthorizedError):
        svc.verify_agent(session, "fp-pend")
    with pytest.raises(svc.AgentNotAuthorizedError):
        svc.verify_agent(session, "fp-nope")


def test_heartbeat_flips_to_online(session, tenant):
    agent = _agent(session, tenant, status="approved", fingerprint="fp-hb")
    svc.heartbeat(session, agent)
    assert agent.status == "online"
    assert agent.last_heartbeat_at is not None


def test_seal_secrets_roundtrips_to_agent_key(session, tenant):
    priv, pub = _keypair()
    agent = _agent(session, tenant, status="approved", fingerprint="fp-seal", public_key=pub)
    secrets_svc.put_secret(session, "master", tenant.id, "pg_main", "postgres://dsn")

    sealed = svc.seal_secrets_for_agent(session, agent, ["pg_main"], "master")
    assert sealed["pg_main"] != "postgres://dsn"  # sealed, not plaintext
    assert decrypt_for_agent(priv, sealed["pg_main"]) == "postgres://dsn"
