"""SQLAlchemy models mirroring database/schema.sql exactly."""

from app.models.alert import Alert, AlertSeverity
from app.models.consumption import ConsumptionRecord
from app.models.cylinder import Cylinder
from app.models.device import Device
from app.models.prediction import Prediction
from app.models.reading import SensorReading
from app.models.safety import SafetyEvent
from app.models.setting import Setting
from app.models.user import User

__all__ = [
    "Alert",
    "AlertSeverity",
    "ConsumptionRecord",
    "Cylinder",
    "Device",
    "Prediction",
    "SensorReading",
    "SafetyEvent",
    "Setting",
    "User",
]
