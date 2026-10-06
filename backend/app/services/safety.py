"""Gas threshold crossings, recorded as events with actuator state.

Two rules shape this module.

**Only commanded state is recorded.** `buzzer_status` and `relay_status` say what the
backend asked for, or what the device reported back. Nothing here infers that gas
physically stopped flowing - the relay may be jammed, unwired, or the whole board
unplugged. The UI shows these as "commanded", never as a confirmed shutoff, and the
words in `app/schemas/monitoring.py` and the README say so too.

**One event per transition, not one per reading.** At a 30-second interval a
sustained leak would otherwise produce 120 identical CRITICAL alerts an hour and the
user would stop reading them. An event is written when the state *changes*: safe to
exceeded, or exceeded back to safe.
"""

from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, AlertSeverity, SafetyEvent, SensorReading

# event_type values
LEAK_SUSPECTED = "LEAK_SUSPECTED"
CLEARED = "CLEARED"

# Commanded actuator state. "ACTIVATED" means the backend asked the relay to cut
# supply; it is not a claim that supply stopped.
BUZZER_ON = "ON"
BUZZER_OFF = "OFF"
RELAY_ACTIVATED = "ACTIVATED"
RELAY_NORMAL = "NORMAL"


def currently_in_alarm(db: Session, cylinder_id: int) -> bool:
    """True when the last recorded event left the cylinder in an alarm state.

    Derived from the event log rather than a cached flag, so a restarted process
    cannot forget that an alarm is active.
    """
    last = db.execute(
        select(SafetyEvent)
        .where(SafetyEvent.cylinder_id == cylinder_id)
        .order_by(SafetyEvent.created_at.desc(), SafetyEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return last is not None and last.event_type == LEAK_SUSPECTED


def evaluate(
    db: Session,
    cylinder_id: int,
    reading: SensorReading,
    gas_threshold: int,
    anomaly_state: str,
) -> Tuple[Optional[SafetyEvent], Optional[Alert]]:
    """Record a safety transition, if this reading is one.

    Returns (event, alert), either of which may be None when nothing changed.
    """
    gas_value = int(reading.gas_sensor_value)
    exceeded = gas_value >= int(gas_threshold)
    in_alarm = currently_in_alarm(db, cylinder_id)

    if exceeded and not in_alarm:
        event = SafetyEvent(
            cylinder_id=cylinder_id,
            gas_value=gas_value,
            threshold=int(gas_threshold),
            buzzer_status=BUZZER_ON,
            relay_status=RELAY_ACTIVATED,
            event_type=LEAK_SUSPECTED,
        )
        alert = Alert(
            cylinder_id=cylinder_id,
            type="GAS_THRESHOLD_EXCEEDED",
            severity=AlertSeverity.CRITICAL,
            message=(
                f"MQ-6 reading {gas_value} reached the configured threshold of "
                f"{gas_threshold}. Buzzer and shutoff relay commanded on "
                f"({anomaly_state}). Ventilate the area and check for a leak before "
                "resuming use. The MQ-6 is a prototype detector, not a certified "
                "analyser, and the relay state shown is what was commanded, not a "
                "confirmed gas shutoff."
            ),
        )
        db.add_all([event, alert])
        db.flush()
        return event, alert

    if not exceeded and in_alarm:
        event = SafetyEvent(
            cylinder_id=cylinder_id,
            gas_value=gas_value,
            threshold=int(gas_threshold),
            buzzer_status=BUZZER_OFF,
            relay_status=RELAY_NORMAL,
            event_type=CLEARED,
        )
        alert = Alert(
            cylinder_id=cylinder_id,
            type="GAS_THRESHOLD_CLEARED",
            severity=AlertSeverity.INFO,
            message=(
                f"MQ-6 reading returned to {gas_value}, below the threshold of "
                f"{gas_threshold}. Buzzer and relay commanded back to normal."
            ),
        )
        db.add_all([event, alert])
        db.flush()
        return event, alert

    # Still safe, or still in alarm: nothing has changed, so nothing is recorded.
    return None, None


def commanded_state(db: Session, cylinder_id: int) -> Tuple[str, str]:
    """(buzzer, relay) as last recorded, or the device's power-on state."""
    last = db.execute(
        select(SafetyEvent)
        .where(SafetyEvent.cylinder_id == cylinder_id)
        .order_by(SafetyEvent.created_at.desc(), SafetyEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return BUZZER_OFF, RELAY_NORMAL
    return last.buzzer_status, last.relay_status
