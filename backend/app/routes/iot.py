"""The device ingest endpoint.

`async def` with the database work pushed into a threadpool, for one reason: the
broadcast at the end is async, and the ORM is not. A plain `def` route could not
await the WebSocket push, and a fully `async def` route doing synchronous SQLAlchemy
work would block the event loop for every other request while MySQL answered.

Authentication is a shared device key in `X-Device-Key`, checked only when
`DEVICE_API_KEY` is configured. Blank disables it, which is what the demo runs with -
and the README says so, rather than leaving an unauthenticated write endpoint looking
like an oversight.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_db
from app.schemas.ingest import IngestResult, SensorPacket
from app.services import ingest as ingest_service
from app.services import monitoring
from app.websocket.manager import manager

logger = logging.getLogger("cylinguard.iot")

router = APIRouter(prefix="/api/iot", tags=["iot"])


def require_device_key(x_device_key: Optional[str] = Header(default=None)) -> None:
    """Check the shared device key, if one is configured."""
    expected = settings.device_api_key
    if not expected:
        return
    if x_device_key != expected:
        logger.warning("rejected packet: bad or missing X-Device-Key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device key"
        )


@router.post(
    "/sensor-data",
    response_model=IngestResult,
    status_code=status.HTTP_201_CREATED,
    summary="Accept one reading from an ESP32 and run the §31 pipeline",
)
async def ingest_sensor_data(
    packet: SensorPacket,
    _: None = Depends(require_device_key),
    db: Session = Depends(get_db),
) -> IngestResult:
    def work():
        outcome = ingest_service.process(db, packet)
        db.commit()
        # Rebuilt after the commit so the frame carries the stored state, not the
        # in-flight objects.
        payload = monitoring.build_dashboard(db, outcome.cylinder)
        return (
            {
                "reading_id": outcome.reading.id,
                "cylinder_id": outcome.cylinder.id,
                "timestamp": outcome.reading.timestamp,
                "total_weight_kg": float(outcome.reading.total_weight_kg),
                "remaining_kg": float(outcome.remaining_kg),
                "percentage": float(outcome.percentage),
                "level_status": outcome.level_status,
                "smoothed_weight_kg": float(outcome.smoothed_kg),
                "delta_classification": outcome.delta_kind,
                "delta_kg": float(outcome.delta_kg),
                "anomaly_state": outcome.verdict.state,
                "deviation_percent": float(outcome.verdict.deviation_percent),
                "gas_status": "GAS_THRESHOLD_EXCEEDED"
                if outcome.verdict.gas_exceeded
                else "SAFE",
                "buzzer_status": outcome.buzzer_status,
                "relay_status": outcome.relay_status,
                "safety_event_created": outcome.safety_event_created,
                "alerts_created": len(outcome.alerts),
                "prediction_days": float(outcome.prediction.remaining_days)
                if outcome.prediction
                else None,
                "prediction_method": outcome.prediction.method
                if outcome.prediction
                else "NONE",
                "report_interval_seconds": outcome.report_interval_seconds,
            },
            payload,
        )

    try:
        result, payload = await run_in_threadpool(work)
    except ingest_service.UnknownDeviceError as exc:
        # Logged, per spec §53: a rejected packet is a diagnostic, not a silence.
        logger.warning("rejected packet: unknown device_id %r", str(exc))
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown device_id '{packet.device_id}'. Register the device first.",
        )

    # --- 11. broadcast ----------------------------------------------------
    delivered = 0
    if payload is not None:
        delivered = await manager.broadcast(
            result["cylinder_id"], payload.model_dump(mode="json")
        )

    return IngestResult(**result, websocket_clients_notified=delivered)
