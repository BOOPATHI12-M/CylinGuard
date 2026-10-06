"""Demo mode controls.

Two different switches, which is worth being clear about because they look alike:

* `settings.demo_mode` is per cylinder and persisted. It is what the user toggles.
* `DEMO_SIMULATOR_ENABLED` is per process and comes from `.env`. It decides whether
  the background loop runs at all, and defaults to off, because a task that writes
  rows to the database on every server start should be something you opted into.

The response reports both, so a dashboard showing a demo badge can explain why
nothing is moving when the loop is switched off.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.demo import DemoScenarioRequest, DemoStateResponse, DemoToggleRequest
from app.services import demo_state, monitoring, simulator

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _state_response(db: Session, cylinder: Cylinder) -> DemoStateResponse:
    setting = monitoring.get_settings_row(db, cylinder.id)
    state = demo_state.state_for(cylinder.id)
    return DemoStateResponse(
        cylinder_id=cylinder.id,
        demo_mode=bool(setting.demo_mode) if setting else app_settings.demo_mode_default,
        scenario=state.scenario,
        available_scenarios=list(demo_state.SCENARIOS),
        suspended_by_real_device=state.suspended,
        suspended_at=state.suspended_at,
        simulator_running=simulator.is_running(),
        tick_seconds=app_settings.demo_tick_seconds,
        ticks_generated=state.ticks,
        last_tick_at=state.last_tick_at,
    )


@router.get("/{cylinder_id}", response_model=DemoStateResponse)
def get_demo_state(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> DemoStateResponse:
    return _state_response(db, cylinder)


@router.post("/{cylinder_id}/toggle", response_model=DemoStateResponse)
def toggle_demo(
    payload: DemoToggleRequest,
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> DemoStateResponse:
    setting = monitoring.get_settings_row(db, cylinder.id)
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No settings row exists for this cylinder",
        )

    setting.demo_mode = payload.enabled
    if payload.enabled:
        # Enabling is the one action that clears a suspension, so a user who tested
        # with real hardware can deliberately hand control back to the simulator.
        demo_state.resume(cylinder.id)
    db.commit()
    return _state_response(db, cylinder)


@router.post("/{cylinder_id}/scenario", response_model=DemoStateResponse)
def set_scenario(
    payload: DemoScenarioRequest,
    cylinder: Cylinder = Depends(get_owned_cylinder),
    db: Session = Depends(get_db),
) -> DemoStateResponse:
    """Switch the running demo story.

    Takes effect on the next tick. `LOW_LPG` applies a one-off level change then
    continues normally; `LEAK_DETECTED` holds the MQ-6 above its threshold until the
    scenario is switched back.
    """
    demo_state.set_scenario(cylinder.id, payload.scenario)
    return _state_response(db, cylinder)
