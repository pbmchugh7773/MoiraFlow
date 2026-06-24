from flowops_api.workflow import (
    validate_workflow,
    ValidationResult,
    workflow_json_schema,
)

GOOD = """
apiVersion: flowops/v1
kind: Workflow
metadata: { name: daily_import }
spec:
  trigger: { type: manual }
  context: { url: "https://x" }
  jobs:
    - id: fetch
      type: command
      with: { command: "curl {{ context.url }}" }
      outputs: { path: /tmp/data }
    - id: load
      type: command
      needs: [fetch]
      with: { command: "cat {{ jobs.fetch.outputs.path }}" }
"""


def test_good_workflow_is_valid():
    result = validate_workflow(GOOD, "yaml")
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.errors == []


def test_parse_error_becomes_structured_error():
    result = validate_workflow("metadata: [unclosed", "yaml")
    assert result.valid is False
    assert result.errors[0].code == "parse_error"


def test_semantic_errors_aggregated():
    bad = """
apiVersion: flowops/v1
kind: Workflow
metadata: { name: n }
spec:
  trigger: { type: manual }
  jobs:
    - id: a
      type: command
      needs: [ghost]
      with: { command: "echo {{ context.missing }}" }
"""
    result = validate_workflow(bad, "yaml")
    assert result.valid is False
    codes = {e.code for e in result.errors}
    assert "unknown_dependency" in codes
    assert "unknown_context_ref" in codes


def test_json_schema_is_generated():
    schema = workflow_json_schema()
    assert schema["title"] == "WorkflowDefinition"
    assert "properties" in schema
