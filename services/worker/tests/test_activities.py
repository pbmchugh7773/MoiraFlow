import asyncio

import httpx
import pytest

from flowops_worker.activities import execute_rest, run_command_job
from flowops_worker.interpreter import JobRequest


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_execute_rest_returns_status_on_expected():
    def handler(request):
        assert request.method == "GET"
        assert str(request.url) == "https://api.test/x"
        return httpx.Response(200, json={"ok": True})

    async def run():
        async with _mock_client(handler) as client:
            return await execute_rest(
                {"method": "GET", "url": "https://api.test/x", "expect_status": [200]}, client
            )

    assert asyncio.run(run()) == 200


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

    assert asyncio.run(run()) == 201
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
