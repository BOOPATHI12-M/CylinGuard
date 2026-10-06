"""The live dashboard socket.

The token arrives as a query parameter, not an Authorization header, because the
browser WebSocket API cannot set headers. That is a real tradeoff: a URL is likelier
to end up in a log than a header, so the token is never logged here, and the
connection is closed before the handshake completes if it does not check out.

Ownership is verified exactly as the REST routes verify it. Without that, knowing a
cylinder id would be enough to watch someone else's gas usage in real time.
"""

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cylinder
from app.security.jwt import TokenError, decode_access_token
from app.services import monitoring
from app.websocket.manager import manager

logger = logging.getLogger("cylinguard.ws")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/dashboard/{cylinder_id}")
async def dashboard_socket(
    websocket: WebSocket,
    cylinder_id: int,
    token: str = Query(..., description="access_token from /api/auth/login"),
    db: Session = Depends(get_db),
) -> None:
    try:
        user_id = decode_access_token(token)
    except TokenError:
        # 1008 POLICY_VIOLATION. Closed before accept, so no frames are ever sent to
        # an unauthenticated client.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning("ws rejected: bad token for cylinder=%s", cylinder_id)
        return

    cylinder = db.execute(
        select(Cylinder).where(Cylinder.id == cylinder_id, Cylinder.user_id == user_id)
    ).scalar_one_or_none()
    if cylinder is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(
            "ws rejected: user=%s does not own cylinder=%s", user_id, cylinder_id
        )
        return

    await manager.connect(cylinder_id, websocket)
    try:
        # Send current state immediately, so a client that connects between readings
        # has something to render instead of an empty screen until the next packet.
        payload = monitoring.build_dashboard(db, cylinder)
        if payload is not None:
            await websocket.send_json(payload.model_dump(mode="json"))

        while True:
            # Nothing is expected from the client; this receive exists so the server
            # notices a disconnect. A ping from the client is answered with a pong so
            # an idle connection is not reaped by an intermediate proxy.
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(cylinder_id, websocket)
    except Exception:
        logger.exception("ws error on cylinder=%s", cylinder_id)
        manager.disconnect(cylinder_id, websocket)
