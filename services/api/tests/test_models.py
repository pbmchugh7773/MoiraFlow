import pytest
from pydantic import ValidationError as PydValidationError

from moiraflow_api.workflow.models import WorkflowDefinition, Job

VALID = {
    "apiVersion": "moiraflow/v1",
    "kind": "Workflow",
    "metadata": {"name": "daily_import"},
    "spec": {
        "trigger": {"type": "manual"},
        "jobs": [
            {"id": "fetch", "type": "rest", "with": {"method": "GET", "url": "https://x"}},
        ],
    },
}


def test_parses_minimal_valid_workflow():
    wf = WorkflowDefinition.model_validate(VALID)
    assert wf.metadata.name == "daily_import"
    assert wf.spec.jobs[0].id == "fetch"
    assert wf.spec.jobs[0].run_on == "server"  # default


def test_with_keyword_is_aliased():
    job = Job.model_validate({"id": "j1", "type": "command", "with": {"command": "ls"}})
    assert job.with_ == {"command": "ls"}


def test_unknown_key_is_rejected():
    bad = {**VALID, "spec": {**VALID["spec"], "bogus": 1}}
    with pytest.raises(PydValidationError):
        WorkflowDefinition.model_validate(bad)


def test_invalid_job_id_rejected():
    with pytest.raises(PydValidationError):
        Job.model_validate({"id": "Bad ID!", "type": "command", "with": {"command": "ls"}})
