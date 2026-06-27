import glob
import subprocess
import sys
import tempfile

import pytest

from moiraflow_worker.activities import run_command_job
from moiraflow_worker.interpreter import JobRequest
from moiraflow_worker.isolation import apply_limits


def test_apply_limits_caps_cpu_in_child(monkeypatch):
    monkeypatch.setenv("MOIRAFLOW_CMD_CPU_SECONDS", "7")
    out = subprocess.run(
        [sys.executable, "-c", "import resource;print(resource.getrlimit(resource.RLIMIT_CPU)[0])"],
        capture_output=True,
        text=True,
        preexec_fn=apply_limits,
    )
    assert out.stdout.strip() == "7"


def test_command_runs_in_ephemeral_workdir_and_cleans_up():
    # the command prints its cwd; we capture it via an artifact-free side channel:
    # it must be a fresh moiraflow-cmd-* dir, and gone afterwards.
    marker = tempfile.gettempdir()
    before = set(glob.glob(f"{marker}/moiraflow-cmd-*"))
    run_command_job(JobRequest(job_id="j", type="command", inputs={"command": "true"}))
    after = set(glob.glob(f"{marker}/moiraflow-cmd-*"))
    assert before == after  # no leftover ephemeral dirs


def test_cpu_limit_kills_runaway_command(monkeypatch):
    monkeypatch.setenv("MOIRAFLOW_CMD_CPU_SECONDS", "1")
    req = JobRequest(job_id="j", type="command", inputs={"command": "while true; do :; done"})
    with pytest.raises(RuntimeError):
        run_command_job(req)
