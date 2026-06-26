import asyncio

from moiraflow_api.live import ConnectionManager


class FakeWS:
    def __init__(self, fail: bool = False):
        self.accepted = False
        self.sent = []
        self._fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self._fail:
            raise RuntimeError("broken pipe")
        self.sent.append(data)


def test_broadcast_reaches_connected_clients():
    mgr = ConnectionManager()
    a, b = FakeWS(), FakeWS()

    async def run():
        await mgr.connect("exec-1", a)
        await mgr.connect("exec-1", b)
        await mgr.connect("exec-2", FakeWS())
        await mgr.broadcast("exec-1", {"type": "execution_started"})

    asyncio.run(run())
    assert a.accepted and b.accepted
    assert a.sent == [{"type": "execution_started"}]
    assert b.sent == [{"type": "execution_started"}]


def test_disconnect_stops_delivery():
    mgr = ConnectionManager()
    ws = FakeWS()

    async def run():
        await mgr.connect("exec-1", ws)
        mgr.disconnect("exec-1", ws)
        await mgr.broadcast("exec-1", {"type": "x"})

    asyncio.run(run())
    assert ws.sent == []


def test_broken_client_is_dropped_not_raised():
    mgr = ConnectionManager()
    good, bad = FakeWS(), FakeWS(fail=True)

    async def run():
        await mgr.connect("e", good)
        await mgr.connect("e", bad)
        await mgr.broadcast("e", {"type": "x"})  # must not raise despite bad client
        await mgr.broadcast("e", {"type": "y"})

    asyncio.run(run())
    assert {"type": "x"} in good.sent and {"type": "y"} in good.sent
