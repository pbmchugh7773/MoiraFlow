import json

from moiraflow_worker.events import EVENTS_STREAM, publish_to_redis


class FakeRedis:
    def __init__(self):
        self.added = []

    def xadd(self, name, fields, *, maxlen=None, approximate=False):
        self.added.append((name, fields, maxlen, approximate))


def test_publish_appends_to_capped_events_stream():
    client = FakeRedis()
    publish_to_redis(client, {"type": "execution_started", "temporal_workflow_id": "wf-1"})
    assert len(client.added) == 1
    name, fields, maxlen, approximate = client.added[0]
    assert name == EVENTS_STREAM
    assert maxlen is not None and approximate is True  # bounded, approximate trim
    event = json.loads(fields["data"])
    assert event["type"] == "execution_started"
    assert event["temporal_workflow_id"] == "wf-1"
