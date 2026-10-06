"""Gas reading against its threshold, actuator state, and the event history.

`buzzer_status` and `relay_status` are read from the most recent recorded safety
event - that is, from what the backend commanded or the device reported. Nothing
here infers an actuator position from the current gas value, because the UI must
never claim a physical gas shutoff happened when all we know is that we asked for
one. When no event has ever been recorded the fields read OFF / NORMAL, which is
the device's documented power-on state rather than a guess.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder, SafetyEvent
from app.schemas.monitoring import GasStatus, SafetyEventResponse, SafetyResponse
from app.services import monitoring

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.get("/{cylinder_id}", response_model=SafetyResponse)
def get_safety(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    limit: int = Query(default=20, ge=1, le=200, description="How many past events to return"),
    db: Session = Depends(get_db),
) -> SafetyResponse:
    reading = monitoring.latest_reading(db, cylinder.id)
    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No sensor readings recorded for this cylinder yet",
        )

    setting = monitoring.get_settings_row(db, cylinder.id)
    last_event = monitoring.latest_safety_event(db, cylinder.id)
    events = list(
        db.execute(
            select(SafetyEvent)
            .where(SafetyEvent.cylinder_id == cylinder.id)
            .order_by(SafetyEvent.created_at.desc())
            .limit(limit)
        ).scalars()
    )

    return SafetyResponse(
        cylinder_id=cylinder.id,
        gas=GasStatus(**monitoring.gas_view(reading, setting)),
        buzzer_status=last_event.buzzer_status if last_event else "OFF",
        relay_status=last_event.relay_status if last_event else "NORMAL",
        events=[SafetyEventResponse.model_validate(e) for e in events],
    )
