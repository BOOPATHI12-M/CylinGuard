"""Read-side helpers shared by the dashboard, safety, history and consumption routes.

These exist so the same question is not answered two different ways in two
different endpoints. Phase 2a only reads what is already stored; the code that
*writes* consumption records, runs the anomaly ladder and pushes WebSocket frames
belongs to phase 2b.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    ConsumptionRecord,
    Cylinder,
    Device,
    Prediction,
    SafetyEvent,
    SensorReading,
    Setting,
)
from app.services import lpg

# Gas status words. The richer ladder (UNUSUAL_CONSUMPTION / POSSIBLE_LEAK /
# CRITICAL_LEAK) needs consumption history and MQ-6 corroboration, so it is the
# rule engine's job in phase 2b, not something to half-guess here.
GAS_SAFE = "SAFE"
GAS_EXCEEDED = "GAS_THRESHOLD_EXCEEDED"


def get_settings_row(db: Session, cylinder_id: int) -> Optional[Setting]:
    return db.execute(
        select(Setting).where(Setting.cylinder_id == cylinder_id)
    ).scalar_one_or_none()


def get_device(db: Session, cylinder_id: int) -> Optional[Device]:
    return db.execute(
        select(Device).where(Device.cylinder_id == cylinder_id)
    ).scalar_one_or_none()


def latest_reading(db: Session, cylinder_id: int) -> Optional[SensorReading]:
    return db.execute(
        select(SensorReading)
        .where(SensorReading.cylinder_id == cylinder_id)
        .order_by(SensorReading.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_prediction(db: Session, cylinder_id: int) -> Optional[Prediction]:
    return db.execute(
        select(Prediction)
        .where(Prediction.cylinder_id == cylinder_id)
        .order_by(Prediction.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_safety_event(db: Session, cylinder_id: int) -> Optional[SafetyEvent]:
    return db.execute(
        select(SafetyEvent)
        .where(SafetyEvent.cylinder_id == cylinder_id)
        .order_by(SafetyEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def unread_alert_count(db: Session, cylinder_id: int) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Alert)
            .where(Alert.cylinder_id == cylinder_id, Alert.is_read.is_(False))
        ).scalar_one()
    )


def recent_alerts(db: Session, cylinder_id: int, limit: int = 5):
    return list(
        db.execute(
            select(Alert)
            .where(Alert.cylinder_id == cylinder_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        ).scalars()
    )


def lpg_view(cylinder: Cylinder, reading: SensorReading, setting: Optional[Setting]) -> dict:
    """The remaining-gas numbers plus their NORMAL/LOW/CRITICAL word."""
    remaining = lpg.remaining_kg(reading.total_weight_kg, cylinder.empty_weight_kg)
    percent = lpg.percentage(remaining, cylinder.capacity_kg)
    low = setting.low_lpg_threshold if setting else Decimal("20.00")
    critical = setting.critical_lpg_threshold if setting else Decimal("10.00")
    return {
        "total_weight_kg": reading.total_weight_kg,
        "remaining_kg": remaining,
        "percentage": percent,
        "status": lpg.level_status(percent, low, critical),
        "measured_at": reading.timestamp,
        "is_simulated": reading.is_simulated,
    }


def gas_view(reading: SensorReading, setting: Optional[Setting]) -> dict:
    threshold = int(setting.gas_leakage_threshold) if setting else 700
    value = int(reading.gas_sensor_value)
    exceeded = value >= threshold
    return {
        "value": value,
        "threshold": threshold,
        "exceeded": exceeded,
        "status": GAS_EXCEEDED if exceeded else GAS_SAFE,
    }


def gas_status_word(value: int, threshold: int) -> str:
    return GAS_EXCEEDED if int(value) >= int(threshold) else GAS_SAFE


def _window_total(db: Session, cylinder_id: int, since: date) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(ConsumptionRecord.consumption_kg), 0)).where(
            ConsumptionRecord.cylinder_id == cylinder_id,
            ConsumptionRecord.record_date >= since,
        )
    ).scalar_one()
    return Decimal(total)


def consumption_summary(db: Session, cylinder_id: int, today: Optional[date] = None) -> dict:
    """Today / 7-day / 30-day totals plus the running daily average.

    The average comes from the stored `daily_average_kg` of the most recent record
    rather than being recomputed, so every screen quotes the same number the
    prediction was based on.
    """
    today = today or date.today()
    latest = db.execute(
        select(ConsumptionRecord)
        .where(ConsumptionRecord.cylinder_id == cylinder_id)
        .order_by(ConsumptionRecord.record_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    today_row = db.execute(
        select(ConsumptionRecord.consumption_kg).where(
            ConsumptionRecord.cylinder_id == cylinder_id,
            ConsumptionRecord.record_date == today,
        )
    ).scalar_one_or_none()

    days = int(
        db.execute(
            select(func.count())
            .select_from(ConsumptionRecord)
            .where(ConsumptionRecord.cylinder_id == cylinder_id)
        ).scalar_one()
    )

    return {
        "today_kg": Decimal(today_row) if today_row is not None else Decimal("0.000"),
        "average_daily_kg": latest.daily_average_kg if latest else Decimal("0.000"),
        "last_7_days_kg": _window_total(db, cylinder_id, today - timedelta(days=6)),
        "last_30_days_kg": _window_total(db, cylinder_id, today - timedelta(days=29)),
        "days_of_history": days,
    }


def daily_series(db: Session, cylinder_id: int, days: int = 30):
    """Oldest-first daily rows, which is the order a chart wants to plot."""
    rows = list(
        db.execute(
            select(ConsumptionRecord)
            .where(ConsumptionRecord.cylinder_id == cylinder_id)
            .order_by(ConsumptionRecord.record_date.desc())
            .limit(days)
        ).scalars()
    )
    return list(reversed(rows))


def history_page(
    db: Session, cylinder_id: int, page: int, size: int, since: Optional[datetime] = None
) -> Tuple[list, int]:
    """One page of readings, newest first, paginated in SQL.

    `sensor_readings` grows without bound - 2,882 rows after one seeded month, and
    one row every 30 seconds in production. The LIMIT/OFFSET and the COUNT both
    run in the database; nothing loads the whole table to slice it in Python.
    """
    where = [SensorReading.cylinder_id == cylinder_id]
    if since is not None:
        where.append(SensorReading.timestamp >= since)

    total = int(
        db.execute(
            select(func.count()).select_from(SensorReading).where(*where)
        ).scalar_one()
    )
    rows = list(
        db.execute(
            select(SensorReading)
            .where(*where)
            .order_by(SensorReading.timestamp.desc())
            .limit(size)
            .offset((page - 1) * size)
        ).scalars()
    )
    return rows, total


def build_dashboard(db: Session, cylinder: Cylinder):
    """Assemble the whole dashboard payload, or None if nothing has been measured.

    Lives here rather than in the route so the REST response and the WebSocket frame
    are produced by the same code. If they were built separately they would drift,
    and the frontend would have to handle two shapes for one screen.
    """
    from datetime import datetime

    from app.config import settings as app_settings
    from app.schemas.monitoring import (
        AlertResponse,
        ConsumptionSummary,
        CylinderInfo,
        DashboardResponse,
        DeviceInfo,
        GasStatus,
        LpgStatus,
        PredictionResponse,
    )

    reading = latest_reading(db, cylinder.id)
    if reading is None:
        return None

    setting = get_settings_row(db, cylinder.id)
    device = get_device(db, cylinder.id)
    prediction = latest_prediction(db, cylinder.id)
    # Imported here rather than at module scope: safety imports models, and a top-level
    # import would make monitoring and safety depend on each other.
    from app.services.safety import commanded_state

    buzzer, relay = commanded_state(db, cylinder.id)
    now = datetime.now()

    device_info = None
    if device is not None:
        device_info = DeviceInfo(
            device_code=device.device_code,
            status=device.status_at(now, app_settings.device_offline_seconds),
            wifi_status=device.wifi_status,
            last_seen=device.last_seen,
            firmware_version=device.firmware_version,
        )

    prediction_out = None
    if prediction is not None:
        prediction_out = PredictionResponse(
            timestamp=prediction.timestamp,
            remaining_kg=prediction.remaining_kg,
            remaining_days=prediction.remaining_days,
            predicted_depletion_date=prediction.predicted_depletion_date,
            confidence=prediction.confidence,
            method=prediction.method,
            sample_count=prediction.sample_count,
            is_estimate=prediction.method != "ML",
        )

    return DashboardResponse(
        cylinder=CylinderInfo.model_validate(cylinder),
        device=device_info,
        lpg=LpgStatus(**lpg_view(cylinder, reading, setting)),
        gas=GasStatus(**gas_view(reading, setting)),
        consumption=ConsumptionSummary(**consumption_summary(db, cylinder.id)),
        prediction=prediction_out,
        unread_alerts=unread_alert_count(db, cylinder.id),
        recent_alerts=[
            AlertResponse.model_validate(a) for a in recent_alerts(db, cylinder.id)
        ],
        buzzer_status=buzzer,
        relay_status=relay,
        refill_threshold_days=int(setting.prediction_threshold) if setting else 5,
        low_lpg_threshold=setting.low_lpg_threshold if setting else Decimal("20.00"),
        critical_lpg_threshold=setting.critical_lpg_threshold if setting else Decimal("10.00"),
        demo_mode=bool(setting.demo_mode) if setting else app_settings.demo_mode_default,
        # Same clock as every other timestamp in the payload; see decision 13.
        generated_at=now,
    )
