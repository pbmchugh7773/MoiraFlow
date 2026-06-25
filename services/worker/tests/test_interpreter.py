import asyncio

from moiraflow_worker.interpreter import JobRequest, JobResult, run_dag


def _defn(jobs, context=None):
    spec = {"trigger": {"type": "manual"}, "jobs": jobs}
    if context is not None:
        spec["context"] = context
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
