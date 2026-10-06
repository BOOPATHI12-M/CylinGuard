"""The WebSocket registry and the socket's authorisation.

The registry is tested directly with stand-in sockets rather than through a live
connection, because what matters here is the bookkeeping: that cylinders are isolated
from each other and that dead sockets are removed instead of breaking delivery to the
living ones. The end-to-end frame is verified against a real running server.
"""

import pytest

from app.websocket.manager import ConnectionManager


class FakeSocket:
    """Stands in for a WebSocket. `fails=True` models a client that has gone away."""

    def __init__(self, fails: bool = False):
        self.fails = fails
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        if self.fails:
            raise RuntimeError("socket is closed")
        self.sent.append(payload)


async def test_connect_accepts_and_registers():
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect(1, socket)
    assert socket.accepted is True
    assert manager.count(1) == 1


async def test_cylinders_are_isolated():
    """A dashboard watching cylinder 1 must never see cylinder 2's data."""
    manager = ConnectionManager()
    one, two = FakeSocket(), FakeSocket()
    await manager.connect(1, one)
    await manager.connect(2, two)

    delivered = await manager.broadcast(1, {"cylinder": 1})
    assert delivered == 1
    assert one.sent == [{"cylinder": 1}]
    assert two.sent == []


async def test_broadcast_reaches_every_client_on_one_cylinder():
    manager = ConnectionManager()
    sockets = [FakeSocket() for _ in range(3)]
    for socket in sockets:
        await manager.connect(7, socket)

    assert await manager.broadcast(7, {"x": 1}) == 3
    assert all(s.sent == [{"x": 1}] for s in sockets)


async def test_one_dead_socket_does_not_block_the_others():
    """A closed tab must not stop the remaining dashboards updating."""
    manager = ConnectionManager()
    alive_a, dead, alive_b = FakeSocket(), FakeSocket(fails=True), FakeSocket()
    for socket in (alive_a, dead, alive_b):
        await manager.connect(1, socket)

    delivered = await manager.broadcast(1, {"tick": 1})
    assert delivered == 2
    assert manager.count(1) == 2, "the dead socket should have been dropped"
    assert alive_a.sent and alive_b.sent


async def test_broadcast_to_nobody_is_not_an_error():
    manager = ConnectionManager()
    assert await manager.broadcast(999, {"x": 1}) == 0


async def test_disconnect_removes_the_empty_bucket():
    """Otherwise every cylinder ever viewed leaks an empty set for the process life."""
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect(5, socket)
    manager.disconnect(5, socket)
    assert manager.count(5) == 0
    assert manager.total() == 0
    assert 5 not in manager._connections


async def test_disconnecting_twice_is_harmless():
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect(1, socket)
    manager.disconnect(1, socket)
    manager.disconnect(1, socket)
    assert manager.total() == 0


# --- authorisation on the socket -----------------------------------------

def test_socket_without_a_token_is_refused(client, cylinder):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect(f"/ws/dashboard/{cylinder.id}"):
            pass


def test_socket_with_a_bad_token_is_refused(client, cylinder):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/dashboard/{cylinder.id}?token=not.a.jwt"
        ) as socket:
            socket.receive_json()


def test_socket_for_another_users_cylinder_is_refused(client, db, cylinder, auth):
    """Knowing a cylinder id must not be enough to watch someone else's gas use."""
    from starlette.websockets import WebSocketDisconnect

    from tests.conftest import make_cylinder, make_user

    stranger = make_user(db, "ws-stranger@test.local")
    theirs = make_cylinder(db, stranger, "CYL-WS-STRANGER")
    token = auth["Authorization"].split(" ", 1)[1]

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/ws/dashboard/{theirs.id}?token={token}"
        ) as socket:
            socket.receive_json()


def test_authorised_socket_receives_the_current_state_immediately(client, cylinder, auth):
    """A client connecting between readings must not stare at an empty screen."""
    token = auth["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(
        f"/ws/dashboard/{cylinder.id}?token={token}"
    ) as socket:
        frame = socket.receive_json()

    # Same shape as GET /api/dashboard/{id} - one screen, one contract.
    assert frame["cylinder"]["cylinder_code"] == "CYL-TEST-001"
    assert frame["lpg"]["remaining_kg"] == 8.2
    assert frame["lpg"]["status"] == "NORMAL"
    assert frame["gas"]["status"] == "SAFE"


def test_socket_answers_a_ping(client, cylinder, auth):
    token = auth["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(
        f"/ws/dashboard/{cylinder.id}?token={token}"
    ) as socket:
        socket.receive_json()  # the initial state frame
        socket.send_text("ping")
        assert socket.receive_json() == {"type": "pong"}
