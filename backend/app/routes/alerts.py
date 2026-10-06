"""Alert list and mark-as-read."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_owned_cylinder
from app.models import Alert, Cylinder, User
from app.schemas.monitoring import AlertResponse, AlertsResponse
from app.services import monitoring

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/{cylinder_id}", response_model=AlertsResponse)
def list_alerts(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    unread_only: bool = Query(default=False),
    severity: Optional[str] = Query(
        default=None, description="Filter to INFO, WARNING or CRITICAL"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> AlertsResponse:
    where = [Alert.cylinder_id == cylinder.id]
    if unread_only:
        where.append(Alert.is_read.is_(False))
    if severity is not None:
        wanted = severity.strip().upper()
        if wanted not in ("INFO", "WARNING", "CRITICAL"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="severity must be INFO, WARNING or CRITICAL",
            )
        where.append(Alert.severity == wanted)

    rows = list(
        db.execute(
            select(Alert)
            .where(*where)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        ).scalars()
    )

    return AlertsResponse(
        cylinder_id=cylinder.id,
        # The badge count is always the true unread total, not the number of rows
        # that happened to match this page's filters.
        unread_count=monitoring.unread_alert_count(db, cylinder.id),
        items=[AlertResponse.model_validate(r) for r in rows],
    )


@router.post("/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Mark one alert read.

    This route is keyed by alert id, not cylinder id, so it cannot use
    `get_owned_cylinder`. Ownership is instead enforced by joining through the
    alert's cylinder - without that join, any authenticated user could mark any
    other user's alerts as read by guessing ids.
    """
    alert = db.execute(
        select(Alert)
        .join(Cylinder, Cylinder.id == Alert.cylinder_id)
        .where(Alert.id == alert_id, Cylinder.user_id == user.id)
    ).scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    if not alert.is_read:
        alert.is_read = True
        db.commit()
        db.refresh(alert)
    return AlertResponse.model_validate(alert)
