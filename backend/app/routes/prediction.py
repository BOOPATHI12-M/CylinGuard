"""The latest depletion estimate.

This endpoint only *reads* the most recent stored prediction. Producing one is the
job of the ingest pipeline (phase 2b for the arithmetic estimate, phase 6 for the
trained model). The response carries `method` and `is_estimate` so the UI badge is
driven by what actually computed the number, and can never advertise ML for a
model that has not been trained.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.monitoring import PredictionResponse
from app.services import monitoring

router = APIRouter(prefix="/api/prediction", tags=["prediction"])

FIELDS = (
    "timestamp",
    "remaining_kg",
    "remaining_days",
    "predicted_depletion_date",
    "confidence",
    "method",
    "sample_count",
)


@router.get("/{cylinder_id}", response_model=PredictionResponse)
def get_prediction(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> PredictionResponse:
    prediction = monitoring.latest_prediction(db, cylinder.id)
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No prediction has been computed for this cylinder yet",
        )
    return PredictionResponse(
        **{field: getattr(prediction, field) for field in FIELDS},
        is_estimate=prediction.method != "ML",
    )
