"""The main screen, served whole.

One request instead of six, because every one of these panels is on screen at the
same moment and a cold load should not fan out. The payload is assembled by
`services.monitoring.build_dashboard`, which is also what the ingest pipeline pushes
over the WebSocket - one screen, one shape, no drift.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.monitoring import DashboardResponse
from app.services import monitoring

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/{cylinder_id}", response_model=DashboardResponse)
def get_dashboard(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    payload = monitoring.build_dashboard(db, cylinder)
    if payload is None:
        # A cylinder whose device has never reported is a real state, not an error
        # in this endpoint - but there is no dashboard to draw, and filling it with
        # zeros would put numbers on screen that no sensor produced.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No sensor readings recorded for this cylinder yet",
        )
    return payload
