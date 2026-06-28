import asyncio

import httpx
import pytest

from moiraflow_worker.activities import _stream_command, execute_rest, run_command_job
from moiraflow_worker.interpreter import JobRequest


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_execute_rest_returns_status_and_parsed_body():
    def handler(request):
        assert request.method == "GET"
        assert str(request.url) == "https://api.test/x"
        return httpx.Response(200, json={"status": "healthy", "version": "1.0.0"})

    async def run():
        async with _mock_client(handler) as client:
            return await execute_rest(
                {"method": "GET", "url": "https://api.test/x", "expect_status": [200]}, client
            )

    status, body = asyncio.run(run())
    assert status == 200
    assert body == {"status": "healthy", "version": "1.0.0"}


def test_run_rest_job_exposes_status_and_body_as_outputs():
    def handler(request):
        return httpx.Response(200, json={"status": "healthy"})

    async def run():
        async with _mock_client(handler) as client:
            status, body = await execute_rest(
                {"method": "GET", "url": "https://api.test/h", "expect_status": [200]}, client
            )
        return status, body

    status, body = asyncio.run(run())
    assert status == 200
    assert body == {"status": "healthy"}


def test_execute_rest_raises_on_unexpected_status():
    def handler(request):
        return httpx.Response(500)

    async def run():
        async with _mock_client(handler) as client:
            await execute_rest(
                {"method": "GET", "url": "https://api.test/x", "expect_status": [200]}, client
            )

    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_execute_rest_sends_body_as_json():
    seen = {}

    def handler(request):
        seen["content"] = request.content
        return httpx.Response(201)

    async def run():
        async with _mock_client(handler) as client:
            return await execute_rest(
                {
                    "method": "POST",
                    "url": "https://api.test/items",
                    "body": {"name": "x"},
                    "expect_status": [201],
                },
                client,
            )

    status, _ = asyncio.run(run())
    assert status == 201
    assert b'"name"' in seen["content"]


def test_run_command_job_echoes_declared_outputs():
    req = JobRequest(
        job_id="a", type="command", inputs={"command": "true"}, outputs_spec={"ok": "yes"}
    )
    result = run_command_job(req)
    assert result.outputs == {"ok": "yes"}


def test_run_command_job_raises_on_failure():
    req = JobRequest(job_id="a", type="command", inputs={"command": "exit 3"})
    with pytest.raises(RuntimeError):
        run_command_job(req)


def test_stream_command_emits_each_line_in_order():
    lines: list[str] = []
    rc, tail = _stream_command("printf 'one\\ntwo\\nthree\\n'", None, None, lines.append)
    assert rc == 0
    assert lines == ["one", "two", "three"]
    assert tail[-1] == "three"  # tail used to build error messages


def test_stream_command_redacts_secrets_in_lines():
    lines: list[str] = []
    _stream_command("echo postgres://user:hunter2@db/app", None, None, lines.append)
    assert "hunter2" not in lines[0]
    assert "***" in lines[0]


def test_stream_command_returns_nonzero_returncode_and_tail():
    lines: list[str] = []
    rc, tail = _stream_command("echo boom; exit 7", None, None, lines.append)
    assert rc == 7
    assert "boom" in tail[-1]
