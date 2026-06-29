import uuid
from types import SimpleNamespace

from moiraflow_api.services import notifications


def _exec():
    return SimpleNamespace(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_name="nightly",
        trigger_source="cron",
    )


def _defn(rules):
    return {"spec": {"notifications": rules, "jobs": []}}


def _recorder():
    calls = []
    return calls, lambda url, payload: calls.append((url, payload))


def test_fires_only_matching_rules():
    calls, send = _recorder()
    defn = _defn(
        [
            {"on": "failed", "type": "webhook", "url": "http://hooks/fail"},
            {"on": "success", "type": "webhook", "url": "http://hooks/ok"},
            {"on": "always", "type": "webhook", "url": "http://hooks/all"},
        ]
    )
    sent = notifications.dispatch(_exec(), defn, "failed", failed_jobs=["a"], sender=send)
    assert sent == 2  # failed + always
    urls = [u for u, _ in calls]
    assert urls == ["http://hooks/fail", "http://hooks/all"]
    assert calls[0][1]["status"] == "failed"
    assert calls[0][1]["failed_jobs"] == ["a"]
    assert calls[0][1]["workflow_name"] == "nightly"


def test_success_only_fires_success_and_always():
    calls, send = _recorder()
    defn = _defn(
        [
            {"on": "failed", "type": "webhook", "url": "http://x/f"},
            {"on": "success", "type": "webhook", "url": "http://x/s"},
        ]
    )
    notifications.dispatch(_exec(), defn, "success", sender=send)
    assert [u for u, _ in calls] == ["http://x/s"]


def test_no_notifications_is_a_noop():
    calls, send = _recorder()
    assert notifications.dispatch(_exec(), {"spec": {"jobs": []}}, "failed", sender=send) == 0
    assert calls == []


def test_a_failing_webhook_does_not_raise():
    def boom(url, payload):
        raise RuntimeError("connection refused")

    defn = _defn([{"on": "failed", "type": "webhook", "url": "http://dead"}])
    # best-effort: dispatch swallows the error and reports zero delivered
    assert notifications.dispatch(_exec(), defn, "failed", sender=boom) == 0


def test_default_sender_is_monkeypatchable(monkeypatch):
    calls, send = _recorder()
    monkeypatch.setattr(notifications, "_default_sender", send)
    defn = _defn([{"on": "always", "type": "webhook", "url": "http://x/a"}])
    notifications.dispatch(_exec(), defn, "success")  # no explicit sender -> uses default
    assert [u for u, _ in calls] == ["http://x/a"]
