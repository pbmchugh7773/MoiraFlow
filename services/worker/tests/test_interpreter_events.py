import asyncio

from moiraflow_worker.interpreter import JobRequest, JobResult, run_dag


def _defn(jobs):
    return {
        "apiVersion": "moiraflow/v1",
        "kind": "Workflow",
        "metadata": {"name": "n"},
        "spec": {"trigger": {"type": "manual"}, "jobs": jobs},
    }


def _collect_emitter(events):
    async def emit(event):
        events.append(event)

    return emit


async def _ok_run(req: JobRequest) -> JobResult:
    return JobResult(job_id=req.job_id, outputs=dict(req.outputs_spec))


def test_emits_full_lifecycle_for_two_job_chain():
    events = []
    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}, "outputs": {"k": "v"}},
            {"id": "b", "type": "command", "needs": ["a"], "with": {"command": "x"}},
        ]
    )
    asyncio.run(run_dag(defn, {}, _ok_run, emit=_collect_emitter(events)))
    types = [(e["type"], e["job_id"]) for e in events]
    assert types == [
        ("execution_started", None),
        ("job_started", "a"),
        ("job_succeeded", "a"),
        ("job_started", "b"),
        ("job_succeeded", "b"),
        ("execution_finished", None),
    ]
    # succeeded event carries the job outputs
    succeeded_a = next(e for e in events if e["type"] == "job_succeeded" and e["job_id"] == "a")
    assert succeeded_a["payload"]["outputs"] == {"k": "v"}


def test_emits_job_failed_and_execution_failed_on_error():
    events = []

    async def failing(req: JobRequest) -> JobResult:
        raise RuntimeError("boom")

    defn = _defn([{"id": "a", "type": "command", "with": {"command": "x"}}])
    try:
        asyncio.run(run_dag(defn, {}, failing, emit=_collect_emitter(events)))
    except RuntimeError:
        pass
    types = [e["type"] for e in events]
    assert types == ["execution_started", "job_started", "job_failed", "execution_failed"]
    assert "boom" in events[-1]["payload"]["error"]


def test_emit_is_optional_backward_compatible():
    defn = _defn([{"id": "a", "type": "command", "with": {"command": "x"}}])
    result = asyncio.run(run_dag(defn, {}, _ok_run))  # no emit
    assert result["jobs"]["a"]["outputs"] == {}
