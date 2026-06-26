import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from moiraflow_worker.activities import run_sql_job
from moiraflow_worker.interpreter import JobRequest
from moiraflow_worker.secrets import decrypt, redact, resolve_reference


def test_redacts_password_in_urls():
    msg = "could not connect to postgresql+psycopg://user:s3cret@db:5432/x"
    assert "s3cret" not in redact(msg)
    assert "user:***@db" in redact(msg)


def test_decrypt_matches_api_fernet_derivation():
    # same derivation as moiraflow_api.services.secrets
    master = "the-master-key"
    key = base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())
    token = Fernet(key).encrypt(b"dsn://secret")
    assert decrypt(master, token) == "dsn://secret"


def test_resolve_reference_passes_through_direct_dsn():
    assert resolve_reference("sqlite://", "tenant-1") == "sqlite://"


def test_resolve_reference_secret_without_tenant_raises():
    with pytest.raises(RuntimeError):
        resolve_reference("secret://pg_main", None)


def test_run_sql_job_executes_against_direct_dsn():
    req = JobRequest(
        job_id="q",
        type="sql",
        inputs={"connection": "sqlite://", "statement": "select 1"},
        outputs_spec={"ran": "yes"},
    )
    result = run_sql_job(req)
    assert result.outputs == {"ran": "yes"}


def test_run_sql_job_redacts_connection_error():
    req = JobRequest(
        job_id="q",
        type="sql",
        inputs={"connection": "sqlite://", "statement": "select * from nope"},
        outputs_spec={},
    )
    with pytest.raises(RuntimeError) as exc:
        run_sql_job(req)
    assert "sql job failed" in str(exc.value)
