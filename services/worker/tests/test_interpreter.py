import asyncio

import pytest

from moiraflow_worker.interpreter import JobRequest, JobResult, run_dag


def _defn(jobs, context=None, on_error=None):
    spec = {"trigger": {"type": "manual"}, "jobs": jobs}
    if context is not None:
        spec["context"] = context
    if on_error is not None:
        spec["on_error"] = on_error
    return {
        "apiVersion": "moiraflow/v1",
        "kind": "Workflow",
        "metadata": {"name": "n"},
        "spec": spec,
    }


def _record_run(calls):
    """A fake run_job that records call order and echoes declared outputs."""

    async def run_job(req: JobRequest) -> JobResult:
        calls.append(req)
        # echo the rendered declared outputs as the job's outputs
        return JobResult(job_id=req.job_id, outputs=dict(req.outputs_spec))

    return run_job


def test_runs_single_job_and_returns_scope():
    defn = _defn(
        [{"id": "a", "type": "command", "with": {"command": "ls"}, "outputs": {"path": "/tmp/x"}}]
    )
    result = asyncio.run(run_dag(defn, {}, _record_run([])))
    assert result["jobs"]["a"]["outputs"] == {"path": "/tmp/x"}
    assert result["context"] == {}


def test_inputs_are_rendered_before_dispatch():
    calls = []
    defn = _defn(
        [{"id": "a", "type": "command", "with": {"command": "curl {{ context.url }}"}}],
        context={"url": "https://x"},
    )
    asyncio.run(run_dag(defn, {"url": "https://x"}, _record_run(calls)))
    assert calls[0].inputs == {"command": "curl https://x"}


def test_outputs_propagate_to_downstream_job():
    calls = []

    async def run_job(req: JobRequest) -> JobResult:
        calls.append(req)
        if req.job_id == "a":
            return JobResult(job_id="a", outputs={"path": "/tmp/data"})
        return JobResult(job_id=req.job_id, outputs={})

    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "echo"}, "outputs": {"path": "x"}},
            {
                "id": "b",
                "type": "command",
                "needs": ["a"],
                "with": {"command": "cat {{ jobs.a.outputs.path }}"},
            },
        ]
    )
    asyncio.run(run_dag(defn, {}, run_job))
    b_call = next(c for c in calls if c.job_id == "b")
    assert b_call.inputs == {"command": "cat /tmp/data"}


def test_dependency_order_is_respected():
    order = []

    async def run_job(req: JobRequest) -> JobResult:
        order.append(req.job_id)
        return JobResult(job_id=req.job_id, outputs={})

    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}},
            {"id": "b", "type": "command", "needs": ["a"], "with": {"command": "x"}},
            {"id": "c", "type": "command", "needs": ["b"], "with": {"command": "x"}},
        ]
    )
    asyncio.run(run_dag(defn, {}, run_job))
    assert order == ["a", "b", "c"]


def test_declared_context_defaults_are_applied():
    # spec.context provides a default; launching with no input still resolves it.
    calls = []
    defn = _defn(
        [{"id": "a", "type": "command", "with": {"command": "echo {{ context.greeting }}"}}],
        context={"greeting": "hi"},
    )
    asyncio.run(run_dag(defn, {}, _record_run(calls)))
    assert calls[0].inputs == {"command": "echo hi"}


def test_input_context_overrides_declared_default():
    calls = []
    defn = _defn(
        [{"id": "a", "type": "command", "with": {"command": "echo {{ context.greeting }}"}}],
        context={"greeting": "hi"},
    )
    result = asyncio.run(run_dag(defn, {"greeting": "hola"}, _record_run(calls)))
    assert calls[0].inputs == {"command": "echo hola"}
    assert result["context"]["greeting"] == "hola"


def test_job_skipped_when_condition_false():
    calls = []
    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}},
            {
                "id": "b",
                "type": "command",
                "with": {"command": "x"},
                "condition": "{{ context.run_b }}",
            },
        ],
    )
    result = asyncio.run(run_dag(defn, {"run_b": False}, _record_run(calls)))
    assert [c.job_id for c in calls] == ["a"]  # b never dispatched
    assert "b" not in result["jobs"]


def test_skip_cascades_to_downstream_jobs():
    calls = []
    defn = _defn(
        [
            {
                "id": "a",
                "type": "command",
                "with": {"command": "x"},
                "condition": "{{ context.go }}",
            },
            {"id": "b", "type": "command", "needs": ["a"], "with": {"command": "x"}},
        ],
    )
    asyncio.run(run_dag(defn, {"go": False}, _record_run(calls)))
    assert calls == []  # a skipped by condition, b cascade-skipped


def test_job_runs_when_condition_true():
    calls = []
    defn = _defn(
        [
            {
                "id": "a",
                "type": "command",
                "with": {"command": "x"},
                "condition": "{{ context.go }}",
            },
        ],
    )
    asyncio.run(run_dag(defn, {"go": True}, _record_run(calls)))
    assert [c.job_id for c in calls] == ["a"]


def test_skipped_job_emits_event():
    events = []

    async def emit(e):
        events.append(e)

    defn = _defn(
        [{"id": "a", "type": "command", "with": {"command": "x"}, "condition": "false"}],
    )
    asyncio.run(run_dag(defn, {}, _record_run([]), emit=emit))
    skipped = [e for e in events if e["type"] == "job_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["job_id"] == "a"
    assert skipped[0]["payload"]["reason"] == "condition_false"


def _fail_on(fail_ids):
    async def run_job(req: JobRequest) -> JobResult:
        if req.job_id in fail_ids:
            raise RuntimeError(f"{req.job_id} boom")
        return JobResult(job_id=req.job_id, outputs=dict(req.outputs_spec))

    return run_job


def test_default_on_error_fail_aborts_the_run():
    defn = _defn([{"id": "a", "type": "command", "with": {"command": "x"}}])
    with pytest.raises(RuntimeError):
        asyncio.run(run_dag(defn, {}, _fail_on({"a"})))


def test_on_error_continue_tolerates_a_failure_and_finishes():
    # 'a' fails but 'b' is independent — the run completes instead of aborting.
    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}},
            {"id": "b", "type": "command", "with": {"command": "x"}},
        ],
        on_error="continue",
    )
    result = asyncio.run(run_dag(defn, {}, _fail_on({"a"})))
    assert "b" in result["jobs"]  # independent branch ran
    assert "a" not in result["jobs"]  # failed job produced no outputs


def test_on_error_continue_cascade_skips_dependents_of_failed():
    calls = []

    async def run_job(req: JobRequest) -> JobResult:
        calls.append(req.job_id)
        if req.job_id == "a":
            raise RuntimeError("boom")
        return JobResult(job_id=req.job_id, outputs={})

    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}},
            {"id": "b", "type": "command", "needs": ["a"], "with": {"command": "x"}},
            {"id": "c", "type": "command", "with": {"command": "x"}},
        ],
        on_error="continue",
    )
    asyncio.run(run_dag(defn, {}, run_job))
    assert "b" not in calls  # depends on the failed 'a' -> cascade-skipped
    assert "c" in calls  # independent -> still ran


def test_on_error_continue_reports_failed_jobs_in_finish_event():
    events = []

    async def emit(e):
        events.append(e)

    defn = _defn([{"id": "a", "type": "command", "with": {"command": "x"}}], on_error="continue")
    asyncio.run(run_dag(defn, {}, _fail_on({"a"}), emit=emit))
    finished = next(e for e in events if e["type"] == "execution_finished")
    assert finished["payload"]["failed_jobs"] == ["a"]
    assert [e for e in events if e["type"] == "job_failed"]  # the failure was emitted


def test_parallel_branches_run_in_same_batch():
    started = []
    release = asyncio.Event()

    async def run_job(req: JobRequest) -> JobResult:
        started.append(req.job_id)
        if req.job_id in ("b", "c"):
            # both parallel jobs must have started before either finishes
            if len([j for j in started if j in ("b", "c")]) < 2:
                await release.wait()
            else:
                release.set()
        return JobResult(job_id=req.job_id, outputs={})

    defn = _defn(
        [
            {"id": "a", "type": "command", "with": {"command": "x"}},
            {"id": "b", "type": "command", "needs": ["a"], "with": {"command": "x"}},
            {"id": "c", "type": "command", "needs": ["a"], "with": {"command": "x"}},
        ]
    )
    asyncio.run(run_dag(defn, {}, run_job))
    assert set(started) == {"a", "b", "c"}
    # b and c were both started before either returned (true concurrency)
    assert started.index("a") == 0
