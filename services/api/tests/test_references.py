from moiraflow_api.workflow.references import validate_references
from moiraflow_api.workflow.parser import parse_definition


def _wf(jobs, context=None):
    spec = {"trigger": {"type": "manual"}, "jobs": jobs}
    if context is not None:
        spec["context"] = context
    return parse_definition(
        {"apiVersion": "moiraflow/v1", "kind": "Workflow", "metadata": {"name": "n"}, "spec": spec},
        "dict",
    )


def test_valid_output_reference_ok():
    wf = _wf(
        [
            {
                "id": "a",
                "type": "command",
                "with": {"command": "echo hi"},
                "outputs": {"path": "/tmp/x"},
            },
            {
                "id": "b",
                "type": "command",
                "needs": ["a"],
                "with": {"command": "cat {{ jobs.a.outputs.path }}"},
            },
        ]
    )
    assert validate_references(wf) == []


def test_context_reference_ok():
    wf = _wf(
        [{"id": "a", "type": "command", "with": {"command": "echo {{ context.url }}"}}],
        context={"url": "https://x"},
    )
    assert validate_references(wf) == []


def test_unknown_context_ref_detected():
    wf = _wf([{"id": "a", "type": "command", "with": {"command": "echo {{ context.missing }}"}}])
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_context_ref" in codes


def test_output_ref_to_undeclared_output_detected():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "echo"}},
            {
                "id": "b",
                "type": "command",
                "needs": ["a"],
                "with": {"command": "cat {{ jobs.a.outputs.path }}"},
            },
        ]
    )
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_output_ref" in codes


def test_output_ref_without_needs_detected():
    wf = _wf(
        [
            {
                "id": "a",
                "type": "command",
                "with": {"command": "echo"},
                "outputs": {"path": "/tmp/x"},
            },
            {"id": "b", "type": "command", "with": {"command": "cat {{ jobs.a.outputs.path }}"}},
        ]
    )
    codes = [e.code for e in validate_references(wf)]
    assert "unknown_output_ref" in codes


def test_nondeterministic_template_rejected():
    wf = _wf([{"id": "a", "type": "command", "with": {"command": "echo {{ now() }}"}}])
    codes = [e.code for e in validate_references(wf)]
    assert "nondeterministic_template" in codes


def test_secret_reference_is_allowed_here():
    # secret existence is checked later in `simulate`, not in structural validation.
    wf = _wf(
        [
            {
                "id": "a",
                "type": "sql",
                "with": {"connection": "secret://pg_main", "statement": "SELECT 1"},
            }
        ]
    )
    assert validate_references(wf) == []


def test_reference_nested_in_dict_and_list_is_scanned():
    wf = _wf(
        [
            {
                "id": "a",
                "type": "rest",
                "with": {
                    "method": "POST",
                    "url": "https://x",
                    "headers": {"X": "{{ context.missing }}"},
                    "body": ["{{ context.also_missing }}"],
                },
            }
        ]
    )
    codes = [e.code for e in validate_references(wf)]
    assert codes.count("unknown_context_ref") == 2


def test_auto_outputs_are_referenceable_without_declaration():
    # rest's status/body and file_transfer's size/artifact_key are produced at runtime;
    # downstream references must validate even though they aren't declared.
    wf = _wf(
        [
            {"id": "fetch", "type": "rest", "with": {"method": "GET", "url": "https://x"}},
            {
                "id": "move",
                "type": "file_transfer",
                "with": {"source": "https://x/a", "destination": "artifact://a"},
            },
            {
                "id": "use",
                "type": "command",
                "needs": ["fetch", "move"],
                "with": {
                    "command": "echo {{ jobs.fetch.outputs.body }} {{ jobs.move.outputs.size }}"
                },
            },
        ]
    )
    assert validate_references(wf) == []
