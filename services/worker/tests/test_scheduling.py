from moiraflow_worker.scheduling import ready_jobs

JOBS = [
    {"id": "a", "type": "command", "with": {"command": "ls"}},
    {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
    {"id": "c", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
    {"id": "d", "type": "command", "with": {"command": "ls"}, "needs": ["b", "c"]},
]


def _ids(jobs):
    return [j["id"] for j in jobs]


def test_initial_ready_set_is_roots():
    assert _ids(ready_jobs(JOBS, completed=set(), running=set())) == ["a"]


def test_parallel_branches_become_ready_together():
    # after 'a' completes, both 'b' and 'c' are ready (diamond fan-out).
    assert _ids(ready_jobs(JOBS, completed={"a"}, running=set())) == ["b", "c"]


def test_join_waits_for_all_dependencies():
    # 'd' needs both b and c; only b done -> d not ready.
    assert _ids(ready_jobs(JOBS, completed={"a", "b"}, running=set())) == ["c"]
    assert _ids(ready_jobs(JOBS, completed={"a", "b", "c"}, running=set())) == ["d"]


def test_running_jobs_are_not_rescheduled():
    assert ready_jobs(JOBS, completed={"a"}, running={"b", "c"}) == []


def test_completed_jobs_are_not_rescheduled():
    assert ready_jobs(JOBS, completed={"a", "b", "c", "d"}, running=set()) == []
