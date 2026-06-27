"""Resource limits for `command` jobs (docs 05 §4.4).

`apply_limits` is a subprocess preexec_fn (Unix) that caps CPU time, address space
and file size before the command runs, so a runaway job can't exhaust the host.
Limits are configurable via env; the working dir is ephemeral (managed by the
activity). True per-job container isolation is Phase 2; running the worker as a
non-root user (Dockerfile) covers the "unprivileged" requirement for the MVP.
"""

from __future__ import annotations

import os


def _bytes(env_var: str, default_mb: int) -> int:
    return int(os.getenv(env_var, str(default_mb))) * 1024 * 1024


def apply_limits() -> None:  # pragma: no cover - runs in the forked child
    import resource

    cpu = int(os.getenv("MOIRAFLOW_CMD_CPU_SECONDS", "30"))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    fsize = _bytes("MOIRAFLOW_CMD_FSIZE_MB", 200)
    resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
    try:
        mem = _bytes("MOIRAFLOW_CMD_MEMORY_MB", 1024)
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    except (ValueError, OSError):  # some platforms reject RLIMIT_AS
        pass
