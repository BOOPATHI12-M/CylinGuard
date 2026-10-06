"""Response models for the read endpoints.

Quantities are declared as `float` even though the columns and the service layer
use `Decimal`. Decimal is right for the arithmetic; float is right on the wire,
because pydantic would otherwise emit Decimal as a JSON string and every consumer
would have to parse it. Values are already rounded by the service layer before
they get here (3dp for kg, 1dp for percentages).

Every status field is a word, never a colour. The frontend renders the word
alongside whatever colour it chooses, so a green dot always reads SAFE.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CylinderInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cylinder_code: str
    empty_weight_kg: float
    capacity_kg: float


class DeviceInfo(BaseModel):
    device_code: str
    # ONLINE / OFFLINE, derived from last_seen at request time rather than stored,
    # so it can never be a stale value left behind by a crashed process.
    status: str
    wifi_status: str
    last_seen: Optional[datetime]
    firmware_version: Optional[str]


class LpgStatus(BaseModel):
    total_weight_kg: float
    remaining_kg: float
    percentage: float
    # NORMAL / LOW / CRITICAL against the per-cylinder thresholds.
    status: str
    measured_at: datetime
    # True when this reading came from the simulator rather than real hardware.
    is_simulated: bool


class GasStatus(BaseModel):
    value: int
    threshold: int
    exceeded: bool
    # SAFE / GAS_THRESHOLD_EXCEEDED. The full escalation ladder
    # (UNUSUAL_CONSUMPTION / POSSIBLE_LEAK / CRITICAL_LEAK) is computed by the
    # rule engine in phase 2b; this endpoint reports only what is stored.
    status: str


class ConsumptionSummary(BaseModel):
    today_kg: float
    average_daily_kg: float
    last_7_days_kg: float
    last_30_days_kg: float
    days_of_history: int


class DailyConsumption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_date: date
    consumption_kg: float
    daily_average_kg: float


class ConsumptionResponse(BaseModel):
    cylinder_id: int
    summary: ConsumptionSummary
    daily: List[DailyConsumption]


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    remaining_kg: float
    remaining_days: float
    predicted_depletion_date: Optional[date]
    confidence: float
    # "ML" once a model is trained (phase 6), "FALLBACK" for the arithmetic
    # estimate. The frontend badge is driven by this field, so it can never claim
    # a model that does not exist.
    method: str
    sample_count: int
    # True whenever method is not ML - the UI shows an ESTIMATE badge.
    is_estimate: bool


class SafetyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    gas_value: int
    threshold: int
    # Recorded state only: what the backend commanded or the device reported.
    # Never an assumption that gas physically stopped flowing.
    buzzer_status: str
    relay_status: str
    event_type: str


class SafetyResponse(BaseModel):
    cylinder_id: int
    gas: GasStatus
    buzzer_status: str
    relay_status: str
    events: List[SafetyEventResponse]


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    type: str
    severity: str
    message: str
    is_read: bool


class AlertsResponse(BaseModel):
    cylinder_id: int
    unread_count: int
    items: List[AlertResponse]


class ReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    total_weight_kg: float
    remaining_kg: float
    percentage: float
    gas_sensor_value: int
    gas_status: str
    device_status: str
    is_simulated: bool


class HistoryPage(BaseModel):
    cylinder_id: int
    items: List[ReadingResponse]
    total: int
    page: int
    size: int
    pages: int


class DashboardResponse(BaseModel):
    """Everything the main screen needs, in one request.

    The dashboard is the one screen that would otherwise fan out into six calls
    on load, so it is served whole. The same shape is pushed over the WebSocket
    in phase 2b.
    """

    cylinder: CylinderInfo
    device: Optional[DeviceInfo]
    lpg: LpgStatus
    gas: GasStatus
    consumption: ConsumptionSummary
    prediction: Optional[PredictionResponse]
    unread_alerts: int
    recent_alerts: List[AlertResponse]
    demo_mode: bool
    generated_at: datetime


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cylinder_id: int
    low_lpg_threshold: float
    critical_lpg_threshold: float
    gas_leakage_threshold: int
    anomaly_threshold: float
    measurement_interval: int
    prediction_threshold: int
    demo_mode: bool
    updated_at: datetime


class SettingsUpdate(BaseModel):
    """Partial update. Every field optional; only what is sent is changed.

    Bounds mirror the CHECK constraints in database/schema.sql so a bad value is
    rejected with a readable 422 instead of an opaque IntegrityError from MySQL.
    Nothing secret is accepted here - this model is the whole of what the Settings
    page is allowed to write.
    """

    low_lpg_threshold: Optional[float] = Field(default=None, gt=0, le=100)
    critical_lpg_threshold: Optional[float] = Field(default=None, gt=0, le=100)
    gas_leakage_threshold: Optional[int] = Field(default=None, gt=0, le=4095)
    anomaly_threshold: Optional[float] = Field(default=None, gt=0, le=999)
    measurement_interval: Optional[int] = Field(default=None, gt=0, le=86400)
    prediction_threshold: Optional[int] = Field(default=None, ge=0, le=365)
    demo_mode: Optional[bool] = None


class CylinderSummary(BaseModel):
    """One row in the cylinder picker.

    Carries enough derived state for the selector to show a level and a status word
    without the frontend having to fetch a dashboard per cylinder.
    """

    id: int
    cylinder_code: str
    empty_weight_kg: float
    capacity_kg: float
    # None until the device has reported at least once. The selector shows "no data"
    # rather than 0%, which would look like an empty cylinder.
    remaining_kg: Optional[float]
    percentage: Optional[float]
    status: Optional[str]
    device_status: Optional[str]
    has_readings: bool
    demo_mode: bool
    last_reading_at: Optional[datetime]
