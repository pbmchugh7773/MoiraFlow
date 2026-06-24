import pytest

from flowops_api.workflow.parser import parse_definition, ParseError

YAML = """
apiVersion: flowops/v1
kind: Workflow
metadata:
  name: daily_import
spec:
  trigger:
    type: manual
  jobs:
    - id: fetch
      type: rest
      with: { method: GET, url: "https://x" }
"""


def test_parses_yaml():
    wf = parse_definition(YAML, "yaml")
    assert wf.spec.jobs[0].id == "fetch"


def test_parses_json_string():
    import json

    wf = parse_definition(
        json.dumps(
            {
                "apiVersion": "flowops/v1",
                "kind": "Workflow",
                "metadata": {"name": "n"},
                "spec": {
                    "trigger": {"type": "manual"},
                    "jobs": [{"id": "j", "type": "command", "with": {"command": "ls"}}],
                },
            }
        ),
        "json",
    )
    assert wf.spec.jobs[0].type == "command"


def test_malformed_yaml_raises_parse_error():
    with pytest.raises(ParseError):
        parse_definition("metadata: [unclosed", "yaml")


def test_schema_violation_raises_parse_error():
    with pytest.raises(ParseError):
        parse_definition("apiVersion: flowops/v1\nkind: Workflow\n", "yaml")
