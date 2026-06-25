import pytest

from moiraflow_worker.templating import (
    RenderScope,
    TemplateError,
    render_job_inputs,
    render_template,
)


def _scope(context=None, outputs=None):
    return RenderScope(context=context or {}, outputs=outputs or {})


def test_renders_context_reference():
    scope = _scope(context={"url": "https://x"})
    assert render_template("curl {{ context.url }}", scope) == "curl https://x"


def test_renders_job_output_reference():
    scope = _scope(outputs={"fetch": {"path": "/tmp/data"}})
    assert render_template("cat {{ jobs.fetch.outputs.path }}", scope) == "cat /tmp/data"


def test_whole_string_single_expression_preserves_type():
    scope = _scope(context={"count": 5})
    # A string that is exactly one expression keeps the original (non-string) value.
    assert render_template("{{ context.count }}", scope) == 5


def test_mixed_text_is_string_interpolated():
    scope = _scope(context={"count": 5})
    assert render_template("n={{ context.count }}", scope) == "n=5"


def test_unknown_reference_raises():
    with pytest.raises(TemplateError):
        render_template("{{ context.missing }}", _scope())


def test_value_without_template_is_unchanged():
    # secret:// values carry no braces and must pass through untouched (late resolution).
    scope = _scope()
    assert render_template("secret://pg_main", scope) == "secret://pg_main"


def test_render_job_inputs_recurses_dict_and_list():
    scope = _scope(context={"url": "https://x", "n": 3})
    rendered = render_job_inputs(
        {
            "method": "POST",
            "url": "{{ context.url }}",
            "headers": {"X-Count": "count={{ context.n }}"},
            "body": ["{{ context.n }}"],
        },
        scope,
    )
    assert rendered == {
        "method": "POST",
        "url": "https://x",
        "headers": {"X-Count": "count=3"},
        "body": [3],  # whole-string expression preserves int type
    }
