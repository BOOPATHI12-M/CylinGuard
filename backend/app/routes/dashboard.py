"""The main screen, served whole.

One request instead of six, because every one of these panels is on screen at the
same moment and a cold load should not fan out. Phase 2b pushes this same shape
over the WebSocket, so the frontend binds to one contract either way.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.monitoring import (
    AlertResponse,
    ConsumptionSummary,
    CylinderInfo,
    DashboardResponse,
    DeviceInfo,
    GasStatus,
    LpgStatus,
    PredictionResponse,
)
from app.services import monitoring

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/{cylinder_id}", response_model=DashboardResponse)
def get_dashboard(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    reading = monitoring.latest_reading(db, cylinder.id)
    if reading is None:
        # A cylinder with no readings is a real state (a device that has never
        # reported), not an error in this endpoint - but there is no dashboard to
        # draw, and inventing zeros would be a hardcoded value on screen.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No sensor readings recorded for this cylinder yet",
        )

    setting = monitoring.get_settings_row(db, cylinder.id)
    device = monitoring.get_device(db, cylinder.id)
    prediction = monitoring.latest_prediction(db, cylinder.id)
    now = datetime.now()

    device_info = None
    if device is not None:
        device_info = DeviceInfo(
            device_code=device.device_code,
            status=device.status_at(now, app_settings.device_offline_seconds),
            wifi_status=device.wifi_status,
            last_seen=device.last_seen,
            firmware_version=device.firmware_version,
        )

    prediction_out = None
    if prediction is not None:
        prediction_out = PredictionResponse(
            **{
                c: getattr(prediction, c)
                for c in (
                    "timestamp",
                    "remaining_kg",
                    "remaining_days",
                    "predicted_depletion_date",
                    "confidence",
                    "method",
                    "sample_count",
                )
            },
            is_estimate=prediction.method != "ML",
        )

    return DashboardResponse(
        cylinder=CylinderInfo.model_validate(cylinder),
        device=device_info,
        lpg=LpgStatus(**monitoring.lpg_view(cylinder, reading, setting)),
        gas=GasStatus(**monitoring.gas_view(reading, setting)),
        consumption=ConsumptionSummary(
            **monitoring.consumption_summary(db, cylinder.id)
        ),
        prediction=prediction_out,
        unread_alerts=monitoring.unread_alert_count(db, cylinder.id),
        recent_alerts=[
            AlertResponse.model_validate(a)
            for a in monitoring.recent_alerts(db, cylinder.id)
        ],
        demo_mode=bool(setting.demo_mode) if setting else app_settings.demo_mode_default,
        # Same clock as every other timestamp in this payload. The DATETIME columns
        # are timezone-naive and written in local time, so returning a UTC instant
        # here would put two different clocks in one response and the frontend
        # would show a reading "22 minutes in the future". Settling on a single
        # timezone convention across the schema is a phase 2b decision.
        generated_at=datetime.now(),
    )
