"""Model status and on-demand training.

Training is a POST because it writes an artifact to disk, and it is authenticated and
cylinder-scoped like everything else - an unauthenticated endpoint that spawns a fit would
be a free CPU sink.

It runs in a threadpool: fitting 200 trees is CPU-bound and would otherwise block the event
loop, stalling every WebSocket frame for the duration.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.dependencies import get_current_user, get_owned_cylinder
from app.models import Cylinder, User
from app.schemas.ml import ModelStatusResponse, TrainingResponse
from app.services import prediction

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/status", response_model=ModelStatusResponse)
def get_status(_: User = Depends(get_current_user)) -> ModelStatusResponse:
    """Whether a model exists, and what its last training reported."""
    return ModelStatusResponse(**prediction.model_status())


@router.post("/train/{cylinder_id}", response_model=TrainingResponse)
async def train(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> TrainingResponse:
    def work():
        return prediction.train_cylinder(db, cylinder.id, cylinder.empty_weight_kg)

    report = await run_in_threadpool(work)

    if report is None:
        # Not an error: too little history is a real state, and the arithmetic path is
        # already serving predictions. 409 rather than 422 - the request was fine, the
        # data is not ready.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Not enough history to train. More complete days of consumption are "
                "needed; the arithmetic estimate continues to be used until then."
            ),
        )

    return TrainingResponse(
        trained=True,
        beats_baseline=report.beats_baseline,
        report=report.__dict__,
    )
