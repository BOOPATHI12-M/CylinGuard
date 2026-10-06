"""List the caller's cylinders.

Added in phase 5 because every other route takes a cylinder id and nothing told the
frontend which ids exist. Without it the shell had `ACTIVE_CYLINDER_ID = 1` hardcoded,
which meant a newly registered user saw a 404 with no explanation and no account could
ever have a second cylinder.

The per-cylinder latest reading is fetched in a loop rather than with a window function.
A household has one or two cylinders, so the clarity is worth more than saving a query;
if a fleet view ever arrives this becomes a single lateral join.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Cylinder, User
from app.schemas.monitoring import CylinderSummary
from app.services import lpg, monitoring

router = APIRouter(prefix="/api/cylinders", tags=["cylinders"])


@router.get("", response_model=list[CylinderSummary])
def list_cylinders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CylinderSummary]:
    cylinders = list(
        db.execute(
            select(Cylinder)
            .where(Cylinder.user_id == user.id)
            .order_by(Cylinder.cylinder_code)
        ).scalars()
    )

    now = datetime.now()
    summaries: list[CylinderSummary] = []
    for cylinder in cylinders:
        reading = monitoring.latest_reading(db, cylinder.id)
        setting = monitoring.get_settings_row(db, cylinder.id)
        device = monitoring.get_device(db, cylinder.id)

        remaining = percentage = status = None
        if reading is not None:
            remaining = lpg.remaining_kg(reading.total_weight_kg, cylinder.empty_weight_kg)
            percentage = lpg.percentage(remaining, cylinder.capacity_kg)
            status = lpg.level_status(
                percentage,
                setting.low_lpg_threshold if setting else 20,
                setting.critical_lpg_threshold if setting else 10,
            )

        summaries.append(
            CylinderSummary(
                id=cylinder.id,
                cylinder_code=cylinder.cylinder_code,
                empty_weight_kg=cylinder.empty_weight_kg,
                capacity_kg=cylinder.capacity_kg,
                remaining_kg=remaining,
                percentage=percentage,
                status=status,
                # Derived per request from last_seen, never stored.
                device_status=(
                    device.status_at(now, app_settings.device_offline_seconds)
                    if device is not None
                    else None
                ),
                has_readings=reading is not None,
                demo_mode=bool(setting.demo_mode) if setting else app_settings.demo_mode_default,
                last_reading_at=reading.timestamp if reading is not None else None,
            )
        )
    return summaries
