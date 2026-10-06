"""Daily consumption totals and the series the charts plot."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.monitoring import (
    ConsumptionResponse,
    ConsumptionSummary,
    DailyConsumption,
)
from app.services import monitoring

router = APIRouter(prefix="/api/consumption", tags=["consumption"])


@router.get("/{cylinder_id}", response_model=ConsumptionResponse)
def get_consumption(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="How many of the most recent daily records to return (7 / 30 / 90 drive the chart tabs)",
    ),
    db: Session = Depends(get_db),
) -> ConsumptionResponse:
    return ConsumptionResponse(
        cylinder_id=cylinder.id,
        summary=ConsumptionSummary(**monitoring.consumption_summary(db, cylinder.id)),
        daily=[
            DailyConsumption.model_validate(r)
            for r in monitoring.daily_series(db, cylinder.id, days)
        ],
    )
