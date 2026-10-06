"""Demo mode request/response models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.demo_state import SCENARIOS


class DemoStateResponse(BaseModel):
    cylinder_id: int
    # The persisted product switch, from settings.demo_mode.
    demo_mode: bool
    # NORMAL / LOW_LPG / LEAK_DETECTED. In-process only; resets on restart.
    scenario: str
    available_scenarios: List[str]
    # True once genuine hardware has reported for this cylinder. Simulation then
    # stays off until demo mode is explicitly re-enabled.
    suspended_by_real_device: bool
    suspended_at: Optional[datetime]
    # Whether the background loop is running at all (DEMO_SIMULATOR_ENABLED).
    simulator_running: bool
    tick_seconds: int
    ticks_generated: int
    last_tick_at: Optional[datetime]


class DemoToggleRequest(BaseModel):
    enabled: bool = Field(description="Turn demo mode on or off for this cylinder")


class DemoScenarioRequest(BaseModel):
    scenario: str = Field(description=f"One of {', '.join(SCENARIOS)}")

    @field_validator("scenario")
    @classmethod
    def _known(cls, value: str) -> str:
        wanted = value.strip().upper()
        if wanted not in SCENARIOS:
            raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
        return wanted
