"""The per-cylinder tunables.

This endpoint is the entire contract of the Settings page, and it deliberately
exposes nothing secret. The `settings` table holds thresholds and intervals only -
no credentials, no JWT secret, no WiFi password - so the row can be returned
verbatim. Anything secret lives in .env and is never reachable from here.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder, Setting
from app.schemas.monitoring import SettingsResponse, SettingsUpdate
from app.services import monitoring

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _require_settings(db: Session, cylinder_id: int) -> Setting:
    setting = monitoring.get_settings_row(db, cylinder_id)
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No settings row exists for this cylinder",
        )
    return setting


@router.get("/{cylinder_id}", response_model=SettingsResponse)
def get_settings(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> SettingsResponse:
    return SettingsResponse.model_validate(_require_settings(db, cylinder.id))


@router.put("/{cylinder_id}", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> SettingsResponse:
    setting = _require_settings(db, cylinder.id)

    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    # The critical threshold is the more urgent of the two, so it has to stay at or
    # below the low threshold. Checked against the post-update values, because
    # either field may be the one being changed.
    low = changes.get("low_lpg_threshold", float(setting.low_lpg_threshold))
    critical = changes.get(
        "critical_lpg_threshold", float(setting.critical_lpg_threshold)
    )
    if critical > low:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "critical_lpg_threshold must be at or below low_lpg_threshold "
                f"(got critical={critical}, low={low})"
            ),
        )

    for field, value in changes.items():
        setattr(setting, field, value)
    db.commit()
    db.refresh(setting)
    return SettingsResponse.model_validate(setting)
