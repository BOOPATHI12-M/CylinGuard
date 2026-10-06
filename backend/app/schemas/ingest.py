"""The ESP32 packet contract.

Validation here is the first step of the §31 pipeline and the only thing standing
between a misbehaving sensor and the database. Spec §53 requires rejected packets to
be logged rather than silently dropped, so the route logs them; this module decides
what counts as rejected.

Bounds come from `app/config.py` rather than being hardcoded, because a 120 kg
plausible-weight ceiling suits a domestic cylinder and not a commercial one.
"""

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings

# A device clock may drift. A little ahead is tolerable; far ahead means a wrong
# clock, and a very old timestamp means a replay or a board that buffered for days.
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_BACKFILL = timedelta(days=7)


class SensorPacket(BaseModel):
    """One reading posted by the device."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(
        max_length=64, description="The device_code, e.g. ESP32-CYL-001"
    )
    total_weight_kg: float = Field(
        description="Gross weight on the load cell, cylinder included"
    )
    gas_sensor_value: int = Field(description="Raw MQ-6 ADC reading")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Device clock. Omit it and the server timestamps the reading.",
    )
    firmware_version: Optional[str] = Field(default=None, max_length=32)
    wifi_status: Optional[str] = Field(default=None, max_length=16)

    @field_validator("device_id")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("device_id must not be blank")
        return value

    @field_validator("total_weight_kg")
    @classmethod
    def _plausible_weight(cls, value: float) -> float:
        if value < 0:
            raise ValueError("total_weight_kg must not be negative")
        if value > settings.max_plausible_weight_kg:
            raise ValueError(
                f"total_weight_kg {value} exceeds the plausible maximum "
                f"{settings.max_plausible_weight_kg} kg - check the load cell calibration"
            )
        return value

    @field_validator("gas_sensor_value")
    @classmethod
    def _plausible_gas(cls, value: int) -> int:
        if value < 0:
            raise ValueError("gas_sensor_value must not be negative")
        if value > settings.max_plausible_gas_value:
            raise ValueError(
                f"gas_sensor_value {value} exceeds the ADC maximum "
                f"{settings.max_plausible_gas_value}"
            )
        return value

    @field_validator("timestamp")
    @classmethod
    def _sane_clock(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        # Column is DATETIME, timezone-naive local time. An offset-aware value is
        # converted rather than rejected, so a correctly-behaved device still works.
        if value.tzinfo is not None:
            value = value.astimezone().replace(tzinfo=None)
        now = datetime.now()
        if value > now + MAX_CLOCK_SKEW:
            raise ValueError("timestamp is in the future - check the device clock")
        if value < now - MAX_BACKFILL:
            raise ValueError("timestamp is more than 7 days old")
        return value


class IngestResult(BaseModel):
    """What the pipeline did with the packet.

    Returned to the device mostly for diagnostics, and asserted against in tests.
    """

    reading_id: int
    cylinder_id: int
    timestamp: datetime
    total_weight_kg: float
    remaining_kg: float
    percentage: float
    level_status: str
    smoothed_weight_kg: float
    # NOISE / CONSUMPTION / REFILL - how the weight change was classified.
    delta_classification: str
    delta_kg: float
    # NORMAL / UNUSUAL_CONSUMPTION / POSSIBLE_LEAK / CRITICAL_LEAK
    anomaly_state: str
    deviation_percent: float
    gas_status: str
    # Commanded state only - never a confirmed physical shutoff.
    buzzer_status: str
    relay_status: str
    safety_event_created: bool
    alerts_created: int
    prediction_days: Optional[float]
    prediction_method: str
    websocket_clients_notified: int
