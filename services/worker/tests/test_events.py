import json

from moiraflow_worker.events import EVENTS_CHANNEL, publish_to_redis


class FakeRedis:
    def __init__(self):
        self.published = []

    def publish(self, channel, message):
        self.published.append((channel, message))


def test_publish_serializes_to_events_channel():
    client = FakeRedis()
    publish_to_redis(client, {"type": "execution_started", "temporal_workflow_id": "wf-1"})
    assert len(client.published) == 1
    channel, message = client.published[0]
    assert channel == EVENTS_CHANNEL
    assert json.loads(message)["type"] == "execution_started"
    assert json.loads(message)["temporal_workflow_id"] == "wf-1"
