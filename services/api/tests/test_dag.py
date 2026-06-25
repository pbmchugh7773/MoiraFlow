from moiraflow_api.workflow.dag import validate_dag, topological_order
from moiraflow_api.workflow.parser import parse_definition


def _wf(jobs):
    return parse_definition(
        {
            "apiVersion": "moiraflow/v1",
            "kind": "Workflow",
            "metadata": {"name": "n"},
            "spec": {"trigger": {"type": "manual"}, "jobs": jobs},
        },
        "dict",
    )


def test_valid_dag_has_no_errors():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "ls"}},
            {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
        ]
    )
    assert validate_dag(wf) == []
    assert topological_order(wf) == ["a", "b"]


def test_duplicate_id_detected():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "ls"}},
            {"id": "a", "type": "command", "with": {"command": "ls"}},
        ]
    )
    codes = [e.code for e in validate_dag(wf)]
    assert "duplicate_job_id" in codes


def test_unknown_dependency_detected():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "ls"}, "needs": ["ghost"]},
        ]
    )
    codes = [e.code for e in validate_dag(wf)]
    assert "unknown_dependency" in codes


def test_cycle_detected():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "ls"}, "needs": ["b"]},
            {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
        ]
    )
    codes = [e.code for e in validate_dag(wf)]
    assert "cycle" in codes


def test_diamond_dag_orders_correctly():
    wf = _wf(
        [
            {"id": "a", "type": "command", "with": {"command": "ls"}},
            {"id": "b", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
            {"id": "c", "type": "command", "with": {"command": "ls"}, "needs": ["a"]},
            {"id": "d", "type": "command", "with": {"command": "ls"}, "needs": ["b", "c"]},
        ]
    )
    assert validate_dag(wf) == []
    order = topological_order(wf)
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")
