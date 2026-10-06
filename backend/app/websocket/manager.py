"""Per-cylinder WebSocket registry.

A dashboard watching cylinder 1 must not receive cylinder 2's frames, so sockets are
bucketed by cylinder id rather than held in one flat list.

Two details that are easy to get wrong:

* **Disconnect cleanup.** A browser tab closed mid-broadcast leaves a socket that
  raises on the next send. Broadcasting collects those failures and removes them,
  rather than letting one dead socket abort delivery to the live ones.
* **Mutating while iterating.** Removal happens after the loop, over a snapshot of
  the set, because discarding entries from a set being iterated raises.

In-process state, deliberately. A single uvicorn worker is what the compose stack
runs; scaling to several would need Redis pub/sub, and pretending otherwise with an
in-memory dict that silently delivers to a third of the clients would be worse than
this limitation being explicit.
"""

import logging
from typing import Dict, List, Set

from fastapi import WebSocket

logger = logging.getLogger("cylinguard.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, cylinder_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(cylinder_id, set()).add(websocket)
        logger.info(
            "ws connected: cylinder=%s clients=%d", cylinder_id, self.count(cylinder_id)
        )

    def disconnect(self, cylinder_id: int, websocket: WebSocket) -> None:
        sockets = self._connections.get(cylinder_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            # Do not leave empty buckets behind for every cylinder ever viewed.
            self._connections.pop(cylinder_id, None)
        logger.info(
            "ws disconnected: cylinder=%s clients=%d", cylinder_id, self.count(cylinder_id)
        )

    def count(self, cylinder_id: int) -> int:
        return len(self._connections.get(cylinder_id, ()))

    def total(self) -> int:
        return sum(len(s) for s in self._connections.values())

    async def broadcast(self, cylinder_id: int, payload: dict) -> int:
        """Send `payload` to every client watching this cylinder.

        Returns how many sockets were delivered to. Dead sockets are dropped, not
        retried: the client will reconnect with backoff and ask for fresh state.
        """
        sockets = self._connections.get(cylinder_id)
        if not sockets:
            return 0

        delivered = 0
        dead: List[WebSocket] = []
        for socket in list(sockets):
            try:
                await socket.send_json(payload)
                delivered += 1
            except Exception:
                # Covers a closed socket, a half-open TCP connection and a client
                # that vanished without a close frame.
                dead.append(socket)

        for socket in dead:
            self.disconnect(cylinder_id, socket)
        if dead:
            logger.info(
                "ws dropped %d dead socket(s) for cylinder=%s", len(dead), cylinder_id
            )
        return delivered


# One registry for the process.
manager = ConnectionManager()
