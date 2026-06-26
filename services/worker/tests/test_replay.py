"""Determinism guard (ADR-0011): replay a recorded interpreter history against the
current workflow code. Fails if the interpreter became non-deterministic or changed
incompatibly. Runs offline (no Temporal server) so it gates every CI build.

To refresh the fixture after an intended interpreter change, capture a fresh
completed FlowInterpreter history with WorkflowHandle.fetch_history().to_json().
"""

import asyncio
from pathlib import Path

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from moiraflow_worker.encryption import data_converter
from moiraflow_worker.workflow import FlowInterpreter

FIXTURE = Path(__file__).parent / "fixtures" / "interpreter_history.json"


def test_interpreter_replays_recorded_history_deterministically():
    history = WorkflowHistory.from_json("replay-check", FIXTURE.read_text())
    # The codec passes plaintext payloads through, so this works for histories
    # captured before or after payload encryption (ADR-0016) was enabled.
    replayer = Replayer(workflows=[FlowInterpreter], data_converter=data_converter())
    # Raises on any non-determinism / incompatible change; returns normally otherwise.
    asyncio.run(replayer.replay_workflow(history))
