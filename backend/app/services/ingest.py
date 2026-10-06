"""The sensor-data pipeline (spec §31), in order.

    validate -> resolve device -> store reading -> compute LPG/% -> smooth
    -> classify delta -> update consumption -> anomaly check -> leak check
    -> update prediction -> create alerts -> broadcast

Validation happens in `schemas/ingest.py` before anything here runs. The one place
this departs from the literal spec ordering is that smoothing is applied *before* the
delta is computed rather than after: a delta between two raw samples is mostly
load-cell noise, so smoothing afterwards would be smoothing the wrong thing.

Alerts are raised on *transitions*, never per reading. At a 30-second interval a
cylinder sitting below 20% would otherwise generate 2,880 identical LOW_LPG alerts a
day, and a user who learns to ignore the alert list will also ignore the leak.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml import predictor
from app.models import (
    Alert,
    AlertSeverity,
    ConsumptionRecord,
    Cylinder,
    Device,
    Prediction,
    SensorReading,
)
from app.schemas.ingest import SensorPacket
from app.config import settings
from app.services import anomaly, consumption, demo_state, lpg, monitoring, safety

logger = logging.getLogger("cylinguard.ingest")


class UnknownDeviceError(Exception):
    """The packet named a device_code that is not registered."""


@dataclass
class PipelineOutcome:
    reading: SensorReading
    cylinder: Cylinder
    remaining_kg: Decimal
    percentage: Decimal
    level_status: str
    smoothed_kg: Decimal
    delta_kind: str
    delta_kg: Decimal
    verdict: anomaly.AnomalyVerdict
    buzzer_status: str
    relay_status: str
    safety_event_created: bool
    alerts: List[Alert]
    prediction: Optional[Prediction]


def resolve_device(db: Session, device_code: str) -> Tuple[Device, Cylinder]:
    """Step 2. An unregistered device is rejected, never auto-provisioned.

    Auto-creating a cylinder for an unknown device_code would let anyone who can
    reach the endpoint fill the database with records nobody owns.
    """
    row = db.execute(
        select(Device, Cylinder)
        .join(Cylinder, Cylinder.id == Device.cylinder_id)
        .where(Device.device_code == device_code)
    ).one_or_none()
    if row is None:
        raise UnknownDeviceError(device_code)
    return row[0], row[1]


def _previous_level_status(
    db: Session, cylinder: Cylinder, low: Decimal, critical: Decimal
) -> Optional[str]:
    """The level word as of the reading before this one, for transition detection."""
    previous = monitoring.latest_reading(db, cylinder.id)
    if previous is None:
        return None
    remaining = lpg.remaining_kg(previous.total_weight_kg, cylinder.empty_weight_kg)
    return lpg.level_status(
        lpg.percentage(remaining, cylinder.capacity_kg), low, critical
    )


def _alerted_today(db: Session, cylinder_id: int, alert_type: str) -> bool:
    """Whether this alert type has already fired today.

    Used for consumption anomalies, which are a property of the day rather than of a
    single reading: once told that today is unusual, the user does not need telling
    again every half minute.
    """
    today = date.today()
    existing = db.execute(
        select(Alert.id)
        .where(Alert.cylinder_id == cylinder_id, Alert.type == alert_type)
        .order_by(Alert.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is None:
        return False
    alert = db.get(Alert, existing)
    return alert is not None and alert.created_at.date() == today


def _upsert_prediction(
    db: Session, cylinder_id: int, estimate: predictor.Estimate
) -> Prediction:
    """One prediction row per day, updated in place.

    Inserting on every packet would add ~2,880 near-identical rows a day and make the
    prediction chart unreadable. The row for today is rewritten instead.
    """
    today = date.today()
    existing = None
    latest = monitoring.latest_prediction(db, cylinder_id)
    if latest is not None and latest.timestamp.date() == today:
        existing = latest

    if existing is None:
        existing = Prediction(cylinder_id=cylinder_id, timestamp=datetime.now())
        db.add(existing)

    existing.timestamp = datetime.now()
    existing.remaining_kg = estimate.remaining_kg
    existing.remaining_days = estimate.remaining_days
    existing.predicted_depletion_date = estimate.predicted_depletion_date
    existing.confidence = estimate.confidence
    existing.method = estimate.method
    existing.sample_count = estimate.sample_count
    db.flush()
    return existing


def process(
    db: Session, packet: SensorPacket, *, simulated: bool = False
) -> PipelineOutcome:
    """Run the pipeline for one validated packet.

    `simulated=True` is passed only by the demo simulator. Everything downstream is
    identical, so demo data exercises the same smoothing, rules and alerts as real
    hardware - the single difference is the `is_simulated` flag stored on the reading,
    which is how a demo number is told from a measurement.
    """
    # --- 2. resolve device -------------------------------------------------
    device, cylinder = resolve_device(db, packet.device_id)
    setting = monitoring.get_settings_row(db, cylinder.id)
    low = setting.low_lpg_threshold if setting else Decimal("20.00")
    critical = setting.critical_lpg_threshold if setting else Decimal("10.00")
    gas_threshold = int(setting.gas_leakage_threshold) if setting else 700
    anomaly_threshold = setting.anomaly_threshold if setting else Decimal("60.00")

    # Captured before the new reading lands, so a transition can be detected.
    previous_status = _previous_level_status(db, cylinder, low, critical)
    previous_weights = consumption.recent_weights(db, cylinder.id)
    previous_smoothed = consumption.smoothed_weight(previous_weights)

    # --- 3. store the reading ---------------------------------------------
    when = packet.timestamp or datetime.now()

    # Was the device considered offline *before* this packet landed? Read now,
    # because updating last_seen below destroys the evidence.
    was_offline = (
        device.status_at(datetime.now(), settings.device_offline_seconds) == "OFFLINE"
    )

    reading = SensorReading(
        cylinder_id=cylinder.id,
        timestamp=when,
        total_weight_kg=Decimal(f"{packet.total_weight_kg:.3f}"),
        gas_sensor_value=packet.gas_sensor_value,
        device_status="ONLINE",
        is_simulated=simulated,
    )
    db.add(reading)

    if not simulated:
        # Genuine hardware takes precedence over the simulator, permanently for this
        # process. See app/services/demo_state.py for why suspension is sticky.
        if demo_state.note_real_packet(cylinder.id):
            logger.info(
                "cylinder=%s real packet received - demo simulation suspended",
                cylinder.id,
            )

    device.last_seen = when
    if packet.wifi_status:
        device.wifi_status = packet.wifi_status
    if packet.firmware_version:
        device.firmware_version = packet.firmware_version
    db.flush()

    # --- 4. LPG and percentage --------------------------------------------
    remaining = lpg.remaining_kg(reading.total_weight_kg, cylinder.empty_weight_kg)
    percentage = lpg.percentage(remaining, cylinder.capacity_kg)
    level_status = lpg.level_status(percentage, low, critical)

    # --- 5. smooth, then classify the change ------------------------------
    smoothed = consumption.smoothed_weight(
        consumption.recent_weights(db, cylinder.id)
    ) or Decimal(reading.total_weight_kg)

    delta_kind, delta_kg = (
        consumption.classify_delta(previous_smoothed, smoothed)
        if previous_smoothed is not None
        else (consumption.NOISE, Decimal("0.000"))
    )

    # --- 6. update the day's consumption ----------------------------------
    consumption.apply_delta(db, cylinder.id, when.date(), delta_kind, delta_kg)

    today_kg = db.execute(
        select(ConsumptionRecord.consumption_kg).where(
            ConsumptionRecord.cylinder_id == cylinder.id,
            ConsumptionRecord.record_date == when.date(),
        )
    ).scalar_one_or_none() or Decimal("0.000")
    average_kg = consumption.daily_average(db, cylinder.id)
    samples = consumption.sample_count(db, cylinder.id)

    # --- 7 + 8. anomaly, then leak check ----------------------------------
    verdict = anomaly.evaluate(
        today_kg=Decimal(today_kg),
        average_kg=average_kg,
        anomaly_threshold_percent=anomaly_threshold,
        gas_value=reading.gas_sensor_value,
        gas_threshold=gas_threshold,
        has_history=samples > 0,
    )

    safety_event, safety_alert = safety.evaluate(
        db, cylinder.id, reading, gas_threshold, verdict.state
    )
    buzzer_status, relay_status = safety.commanded_state(db, cylinder.id)

    # --- 9. prediction ----------------------------------------------------
    estimate = predictor.estimate(
        remaining_kg=remaining,
        average_daily_kg=average_kg,
        sample_count=samples,
        variance=consumption.consumption_variance(db, cylinder.id),
        now=datetime.now(),
    )
    prediction = _upsert_prediction(db, cylinder.id, estimate)

    # --- 10. alerts -------------------------------------------------------
    alerts: List[Alert] = []
    if safety_alert is not None:
        alerts.append(safety_alert)

    if delta_kind == consumption.REFILL:
        alerts.append(
            Alert(
                cylinder_id=cylinder.id,
                type="REFILL_DETECTED",
                severity=AlertSeverity.INFO,
                message=(
                    f"Cylinder refill detected - weight increased by {delta_kg:.2f} kg."
                ),
            )
        )

    # Level alerts only on a transition into a worse state.
    if level_status != previous_status and level_status in (lpg.LOW, lpg.CRITICAL):
        severity = (
            AlertSeverity.CRITICAL if level_status == lpg.CRITICAL else AlertSeverity.WARNING
        )
        threshold = critical if level_status == lpg.CRITICAL else low
        alerts.append(
            Alert(
                cylinder_id=cylinder.id,
                type=f"{level_status}_LPG",
                severity=severity,
                message=(
                    f"LPG at {percentage}% ({remaining} kg), at or below the "
                    f"{threshold}% threshold. "
                    + (
                        "Arrange a refill now."
                        if level_status == lpg.CRITICAL
                        else "Plan a refill."
                    )
                ),
            )
        )

    # A device that had gone quiet is back. Raised here rather than in the sweep
    # because arriving data *is* the transition, and only a real packet counts.
    if was_offline and not simulated:
        alerts.append(
            Alert(
                cylinder_id=cylinder.id,
                type="DEVICE_ONLINE",
                severity=AlertSeverity.INFO,
                message=(
                    f"Device {device.device_code} is reporting again after being "
                    "offline."
                ),
            )
        )

    # Consumption anomaly: once a day, and never described as a leak.
    if verdict.consumption_abnormal and not _alerted_today(
        db, cylinder.id, "ABNORMAL_CONSUMPTION"
    ):
        alerts.append(
            Alert(
                cylinder_id=cylinder.id,
                type="ABNORMAL_CONSUMPTION",
                severity=AlertSeverity.WARNING,
                message=(
                    f"Consumption {verdict.deviation_percent}% above the "
                    f"{average_kg} kg/day average ({today_kg} kg today). This is not "
                    "by itself a leak - check for an unattended burner or a regulator "
                    "fault."
                ),
            )
        )

    for alert in alerts:
        if alert not in db.new:
            db.add(alert)
    db.flush()

    if delta_kind == consumption.IMPLAUSIBLE_DROP:
        # Not an alert type the spec defines, and the dashboard already shows the new
        # level, so this is logged rather than invented as a notification.
        logger.warning(
            "cylinder=%s implausible %.3fkg drop between readings - treated as a "
            "cylinder change or load-cell fault, not consumption",
            cylinder.id,
            float(delta_kg),
        )

    if delta_kind != consumption.NOISE or alerts:
        logger.info(
            "ingest cylinder=%s delta=%s %.3fkg state=%s alerts=%d",
            cylinder.id,
            delta_kind,
            float(delta_kg),
            verdict.state,
            len(alerts),
        )

    return PipelineOutcome(
        reading=reading,
        cylinder=cylinder,
        remaining_kg=remaining,
        percentage=percentage,
        level_status=level_status,
        smoothed_kg=smoothed,
        delta_kind=delta_kind,
        delta_kg=delta_kg,
        verdict=verdict,
        buzzer_status=buzzer_status,
        relay_status=relay_status,
        safety_event_created=safety_event is not None,
        alerts=alerts,
        prediction=prediction,
    )
