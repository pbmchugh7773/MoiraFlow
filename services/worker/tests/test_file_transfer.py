import pytest
from temporalio.exceptions import ApplicationError

from moiraflow_worker import activities
from moiraflow_worker.file_transfer import MAX_BYTES, parse_credentials, parse_uri, transfer
from moiraflow_worker.interpreter import JobRequest


def test_parse_uri_schemes():
    assert parse_uri("https://x.io/a.csv")["scheme"] == "https"
    s3 = parse_uri("s3://mybucket/path/to/key.csv")
    assert s3 == {
        "scheme": "s3",
        "raw": "s3://mybucket/path/to/key.csv",
        "bucket": "mybucket",
        "key": "path/to/key.csv",
    }
    art = parse_uri("artifact://incoming/data.csv")
    assert art["scheme"] == "artifact" and art["key"] == "incoming/data.csv"
    sftp = parse_uri("sftp://user@host.io:2222/in/data.csv")
    assert sftp["host"] == "host.io" and sftp["port"] == 2222
    assert sftp["user"] == "user" and sftp["path"] == "/in/data.csv"


def test_parse_uri_unsupported_scheme_raises():
    with pytest.raises(ValueError):
        parse_uri("ftp://host/x")


def test_parse_credentials():
    assert parse_credentials(None) == {}
    assert parse_credentials('{"username": "u", "password": "p"}') == {
        "username": "u",
        "password": "p",
    }
    assert parse_credentials({"username": "u"}) == {"username": "u"}


def _fakes():
    calls = {}

    def reader(parsed, creds):
        calls["read"] = (parsed, creds)
        return b"hello,world\n"

    def writer(parsed, data, creds, **kw):
        calls["write"] = (parsed, data, creds, kw)
        return {
            "name": "out.csv",
            "bucket": "arts",
            "object_key": "t/out.csv",
            "size_bytes": len(data),
        }

    return calls, {"s3": reader, "https": reader}, {"artifact": writer, "s3": writer}


def test_transfer_reads_source_and_writes_destination():
    calls, readers, writers = _fakes()
    result = transfer(
        "https://x.io/a.csv",
        "artifact://out.csv",
        tenant_id="t1",
        job_id="j1",
        readers=readers,
        writers=writers,
    )
    assert result["size"] == len(b"hello,world\n")
    assert result["ref"]["object_key"] == "t/out.csv"
    # credentials + tenant/job flow through to the writer
    assert calls["write"][3] == {"tenant_id": "t1", "job_id": "j1"}


def test_transfer_unsupported_source_scheme_raises():
    _, readers, writers = _fakes()
    with pytest.raises(ValueError):
        transfer("artifact://x", "s3://b/k", readers=readers, writers=writers)


def test_transfer_unsupported_destination_scheme_raises():
    _, readers, writers = _fakes()
    with pytest.raises(ValueError):
        transfer("https://x.io/a", "sftp://h/p", readers=readers, writers=writers)


def test_transfer_rejects_oversize():
    big = b"x" * (MAX_BYTES + 1)
    readers = {"https": lambda p, c: big}
    writers = {"s3": lambda p, d, c, **k: None}
    with pytest.raises(ValueError):
        transfer("https://x.io/a", "s3://b/k", readers=readers, writers=writers)


def test_run_file_transfer_job_shapes_outputs(monkeypatch):
    # Stub the actual transfer; assert the activity surfaces size + artifact.
    monkeypatch.setattr(
        activities,
        "transfer",
        lambda *a, **k: {
            "size": 42,
            "ref": {
                "object_key": "default/out.csv",
                "name": "out.csv",
                "bucket": "arts",
                "size_bytes": 42,
                "content_type": None,
            },
        },
    )
    req = JobRequest(
        job_id="move",
        type="file_transfer",
        inputs={"source": "https://x.io/a.csv", "destination": "artifact://out.csv"},
    )
    result = activities.run_file_transfer_job(req)
    assert result.outputs["size"] == 42
    assert result.outputs["artifact_key"] == "default/out.csv"
    assert result.artifacts == [
        {
            "object_key": "default/out.csv",
            "name": "out.csv",
            "bucket": "arts",
            "size_bytes": 42,
            "content_type": None,
        }
    ]


def test_run_file_transfer_job_config_error_is_non_retryable(monkeypatch):
    def boom(*a, **k):
        raise ValueError("unsupported scheme")

    monkeypatch.setattr(activities, "transfer", boom)
    req = JobRequest(
        job_id="move",
        type="file_transfer",
        inputs={"source": "ftp://x/a", "destination": "s3://b/k"},
    )
    with pytest.raises(ApplicationError) as exc:
        activities.run_file_transfer_job(req)
    assert exc.value.non_retryable
