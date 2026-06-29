import asyncio

import pytest
from temporalio.exceptions import ApplicationError

from moiraflow_worker.activities import run_transform_job
from moiraflow_worker.interpreter import JobRequest
from moiraflow_worker.transform import extract_path, parse_source, xml_to_obj


def test_parse_json():
    assert parse_source('{"a": 1, "b": [2, 3]}', "json") == {"a": 1, "b": [2, 3]}


def test_parse_csv_to_list_of_dicts():
    rows = parse_source("name,email\nA,a@x.io\nB,b@x.io\n", "csv")
    assert rows == [{"name": "A", "email": "a@x.io"}, {"name": "B", "email": "b@x.io"}]


def test_parse_xml_repeated_tags_become_a_list():
    obj = parse_source(
        "<users><user><email>a@x.io</email></user><user><email>b@x.io</email></user></users>",
        "xml",
    )
    assert obj == {"user": [{"email": "a@x.io"}, {"email": "b@x.io"}]}


def test_parse_passes_through_already_structured_data():
    # e.g. a JSON object templated in from a prior job's output
    assert parse_source({"a": 1}, "json") == {"a": 1}


def test_parse_unsupported_format_raises():
    with pytest.raises(ValueError):
        parse_source("x", "yaml")


def test_xml_leaf_is_text():
    import defusedxml.ElementTree as ET

    assert xml_to_obj(ET.fromstring("<n>hi</n>")) == "hi"


@pytest.mark.parametrize(
    "data, path, expected",
    [
        ({"a": {"b": 5}}, "$.a.b", 5),
        ({"a": 1}, "$", {"a": 1}),
        ([10, 20, 30], "$.length", 3),
        ([10, 20, 30], "$[1]", 20),
        ([{"email": "a@x"}, {"email": "b@x"}], "$[0].email", "a@x"),
        ([{"email": "a@x"}, {"email": "b@x"}], "$[*].email", ["a@x", "b@x"]),
        ({"items": [{"n": 1}, {"n": 2}]}, "items[*].n", [1, 2]),
        ({"length": 7}, "$.length", 7),  # a real "length" key wins over count
    ],
)
def test_extract_path(data, path, expected):
    assert extract_path(data, path) == expected


def test_transform_job_extracts_declared_outputs():
    req = JobRequest(
        job_id="parse",
        type="transform",
        inputs={"format": "csv", "content": "name,email\nA,a@x.io\nB,b@x.io\n"},
        outputs_spec={"rows": "$.length", "first_email": "$[0].email"},
    )
    result = run_transform_job_sync(req)
    assert result.outputs == {"rows": 2, "first_email": "a@x.io"}


def test_transform_job_bad_path_is_non_retryable():
    req = JobRequest(
        job_id="parse",
        type="transform",
        inputs={"format": "json", "content": '{"a": 1}'},
        outputs_spec={"x": "$.missing.deep"},
    )
    with pytest.raises(ApplicationError) as exc:
        run_transform_job_sync(req)
    assert exc.value.non_retryable


def run_transform_job_sync(req: JobRequest):
    return asyncio.run(run_transform_job(req))
