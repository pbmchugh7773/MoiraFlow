from flowops_api.workflow.hashing import definition_hash, canonical_dict
from flowops_api.workflow.parser import parse_definition

BASE = {
    "apiVersion": "flowops/v1",
    "kind": "Workflow",
    "metadata": {"name": "n"},
    "spec": {
        "trigger": {"type": "manual"},
        "jobs": [{"id": "a", "type": "command", "with": {"command": "ls"}}],
    },
}


def test_hash_is_stable_and_hex():
    h = definition_hash(parse_definition(BASE, "dict"))
    assert isinstance(h, str) and len(h) == 64
    assert h == definition_hash(parse_definition(BASE, "dict"))


def test_key_order_does_not_change_hash():
    reordered = {
        "kind": "Workflow",
        "apiVersion": "flowops/v1",
        "spec": BASE["spec"],
        "metadata": {"name": "n"},
    }
    assert definition_hash(parse_definition(BASE, "dict")) == definition_hash(
        parse_definition(reordered, "dict")
    )


def test_semantic_change_changes_hash():
    changed = {**BASE, "metadata": {"name": "different"}}
    assert definition_hash(parse_definition(BASE, "dict")) != definition_hash(
        parse_definition(changed, "dict")
    )


def test_canonical_dict_uses_aliases():
    cd = canonical_dict(parse_definition(BASE, "dict"))
    assert cd["apiVersion"] == "flowops/v1"
    assert cd["spec"]["jobs"][0]["with"] == {"command": "ls"}
