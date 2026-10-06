"""The POST /api/iot/sensor-data pipeline, end to end against the real schema."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Alert, ConsumptionRecord, Prediction, SafetyEvent, SensorReading

PATH = "/api/iot/sensor-data"


def packet(**overrides) -> dict:
    body = {
        "device_id": "ESP32-TEST-001",
        "total_weight_kg": 23.100,
        "gas_sensor_value": 190,
    }
    body.update(overrides)
    return body


def _count(db, model, cylinder_id) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(model).where(model.cylinder_id == cylinder_id)
        ).scalar_one()
    )


# --- the happy path ------------------------------------------------------

def test_packet_is_stored_and_derived(client, db, cylinder):
    before = _count(db, SensorReading, cylinder.id)
    response = client.post(PATH, json=packet())
    assert response.status_code == 201, response.text
    body = response.json()

    assert _count(db, SensorReading, cylinder.id) == before + 1
    # 23.100 total - 15.000 tare = 8.100 kg of gas, of a 14.200 kg capacity.
    assert body["remaining_kg"] == 8.1
    assert body["percentage"] == 57.0
    assert body["level_status"] == "NORMAL"
    assert body["gas_status"] == "SAFE"
    assert body["anomaly_state"] == "NORMAL"
    assert body["prediction_method"] == "FALLBACK"


def test_real_packets_are_not_marked_simulated(client, db, cylinder):
    """`is_simulated` is how a demo reading is told from a measurement."""
    reading_id = client.post(PATH, json=packet()).json()["reading_id"]
    assert db.get(SensorReading, reading_id).is_simulated is False


def test_device_last_seen_and_firmware_are_updated(client, db, cylinder):
    from app.models import Device

    client.post(PATH, json=packet(firmware_version="1.2.3", wifi_status="CONNECTED"))
    device = db.execute(
        select(Device).where(Device.cylinder_id == cylinder.id)
    ).scalar_one()
    assert device.firmware_version == "1.2.3"
    assert (datetime.now() - device.last_seen).total_seconds() < 60


def test_consumption_accumulates_into_one_row_per_day(client, db, cylinder):
    """uq_consumption_cyl_date means repeated packets must update, not insert."""
    for weight in (23.100, 23.000, 22.900):
        client.post(PATH, json=packet(total_weight_kg=weight))

    rows = db.execute(
        select(ConsumptionRecord).where(ConsumptionRecord.cylinder_id == cylinder.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].consumption_kg > Decimal("0.000")


def test_prediction_is_updated_not_appended(client, db, cylinder):
    """2,880 packets a day must not become 2,880 prediction rows."""
    for weight in (23.100, 23.000, 22.900, 22.800):
        client.post(PATH, json=packet(total_weight_kg=weight))
    assert _count(db, Prediction, cylinder.id) == 1


# --- validation (spec §53) ----------------------------------------------

def test_negative_weight_is_rejected(client, cylinder):
    assert client.post(PATH, json=packet(total_weight_kg=-1)).status_code == 422


def test_implausible_weight_is_rejected(client, cylinder):
    """A load cell reporting 500 kg is miscalibrated, not a very full cylinder."""
    assert client.post(PATH, json=packet(total_weight_kg=500)).status_code == 422


def test_negative_gas_is_rejected(client, cylinder):
    assert client.post(PATH, json=packet(gas_sensor_value=-5)).status_code == 422


def test_gas_above_the_adc_range_is_rejected(client, cylinder):
    assert client.post(PATH, json=packet(gas_sensor_value=5000).copy()).status_code == 422


def test_future_timestamp_is_rejected(client, cylinder):
    future = (datetime.now() + timedelta(hours=2)).isoformat()
    assert client.post(PATH, json=packet(timestamp=future)).status_code == 422


def test_ancient_timestamp_is_rejected(client, cylinder):
    old = (datetime.now() - timedelta(days=30)).isoformat()
    assert client.post(PATH, json=packet(timestamp=old)).status_code == 422


def test_unknown_field_is_rejected(client, cylinder):
    """extra='forbid', so a typo in the firmware is caught rather than ignored."""
    assert client.post(PATH, json=packet(weight=23.1)).status_code == 422


def test_unknown_device_is_404_not_auto_provisioned(client, db, cylinder):
    response = client.post(PATH, json=packet(device_id="ESP32-NOT-REGISTERED"))
    assert response.status_code == 404
    assert "Unknown device_id" in response.json()["detail"]


def test_rejected_packet_does_not_store_a_reading(client, db, cylinder):
    before = _count(db, SensorReading, cylinder.id)
    client.post(PATH, json=packet(total_weight_kg=500))
    assert _count(db, SensorReading, cylinder.id) == before


# --- device key ----------------------------------------------------------

def test_device_key_is_enforced_when_configured(client, cylinder, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "device_api_key", "s3cret-device-key")
    assert client.post(PATH, json=packet()).status_code == 401
    assert (
        client.post(PATH, json=packet(), headers={"X-Device-Key": "wrong"}).status_code
        == 401
    )
    assert (
        client.post(
            PATH, json=packet(), headers={"X-Device-Key": "s3cret-device-key"}
        ).status_code
        == 201
    )


# --- safety transitions --------------------------------------------------

def test_leak_raises_one_event_not_one_per_reading(client, db, cylinder):
    """A sustained leak at 30s intervals must not produce 120 alerts an hour."""
    before_events = _count(db, SafetyEvent, cylinder.id)
    before_alerts = _count(db, Alert, cylinder.id)

    for _ in range(4):
        response = client.post(PATH, json=packet(gas_sensor_value=812))
        assert response.status_code == 201

    assert _count(db, SafetyEvent, cylinder.id) == before_events + 1
    assert _count(db, Alert, cylinder.id) == before_alerts + 1

    body = client.post(PATH, json=packet(gas_sensor_value=812)).json()
    assert body["anomaly_state"] == "POSSIBLE_LEAK"
    assert body["safety_event_created"] is False
    assert body["buzzer_status"] == "ON"
    assert body["relay_status"] == "ACTIVATED"


def test_returning_to_safe_records_a_clearing_event(client, db, cylinder):
    client.post(PATH, json=packet(gas_sensor_value=812))
    body = client.post(PATH, json=packet(gas_sensor_value=190)).json()

    assert body["safety_event_created"] is True
    assert body["buzzer_status"] == "OFF"
    assert body["relay_status"] == "NORMAL"

    latest = db.execute(
        select(SafetyEvent)
        .where(SafetyEvent.cylinder_id == cylinder.id)
        .order_by(SafetyEvent.id.desc())
        .limit(1)
    ).scalar_one()
    assert latest.event_type == "CLEARED"


def test_leak_alert_does_not_claim_a_physical_shutoff(client, db, cylinder):
    client.post(PATH, json=packet(gas_sensor_value=812))
    alert = db.execute(
        select(Alert)
        .where(Alert.cylinder_id == cylinder.id, Alert.type == "GAS_THRESHOLD_EXCEEDED")
        .order_by(Alert.id.desc())
        .limit(1)
    ).scalar_one()
    assert "commanded" in alert.message
    assert "not a certified" in alert.message


# --- refill --------------------------------------------------------------

def test_refill_is_detected_and_not_counted_as_consumption(client, db, cylinder):
    before = db.execute(
        select(func.coalesce(func.sum(ConsumptionRecord.consumption_kg), 0)).where(
            ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()

    # Weight jumps from ~23.2 kg to a full 29.0 kg and *stays* there. Detection is
    # on the smoothed series, so a refill is confirmed once the median has moved -
    # a few readings, not instantly. That latency is the price of being immune to a
    # single spurious sample (see the spike test below).
    seen = []
    for _ in range(5):
        seen.append(client.post(PATH, json=packet(total_weight_kg=29.000)).json())
    assert "REFILL" in [b["delta_classification"] for b in seen], [
        b["delta_classification"] for b in seen
    ]

    after = db.execute(
        select(func.coalesce(func.sum(ConsumptionRecord.consumption_kg), 0)).where(
            ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()
    assert Decimal(after) == Decimal(before), "a refill must not add consumption"

    assert db.execute(
        select(Alert).where(
            Alert.cylinder_id == cylinder.id, Alert.type == "REFILL_DETECTED"
        )
    ).scalars().first() is not None


def test_noise_does_not_accumulate(client, db, cylinder):
    """Jitter around a steady weight must add no consumption at all."""
    before = db.execute(
        select(func.coalesce(func.sum(ConsumptionRecord.consumption_kg), 0)).where(
            ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()

    for weight in (23.205, 23.198, 23.203, 23.199, 23.201):
        assert client.post(PATH, json=packet(total_weight_kg=weight)).status_code == 201

    after = db.execute(
        select(func.coalesce(func.sum(ConsumptionRecord.consumption_kg), 0)).where(
            ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()
    assert Decimal(after) == Decimal(before)


# --- low level alerts ----------------------------------------------------

def test_crossing_into_low_alerts_once(client, db, cylinder):
    """20% of 14.2 kg is 2.84 kg, so 17.5 kg total is below the low threshold."""
    first = client.post(PATH, json=packet(total_weight_kg=17.500)).json()
    assert first["level_status"] == "LOW"

    low_alerts = lambda: int(  # noqa: E731
        db.execute(
            select(func.count())
            .select_from(Alert)
            .where(Alert.cylinder_id == cylinder.id, Alert.type == "LOW_LPG")
        ).scalar_one()
    )
    after_first = low_alerts()
    assert after_first >= 1

    # Still low, so no second alert.
    client.post(PATH, json=packet(total_weight_kg=17.450))
    assert low_alerts() == after_first


def test_a_single_wild_sample_is_not_a_refill(client, db, cylinder):
    """Someone leaning on the cylinder must not register as a 35 kg delivery.

    This is why refill detection runs on the smoothed series rather than the raw
    reading, and it is the reason the test above needs several packets.
    """
    body = client.post(PATH, json=packet(total_weight_kg=58.000)).json()
    assert body["delta_classification"] == "NOISE"
    assert db.execute(
        select(Alert).where(
            Alert.cylinder_id == cylinder.id, Alert.type == "REFILL_DETECTED"
        )
    ).scalars().first() is None
