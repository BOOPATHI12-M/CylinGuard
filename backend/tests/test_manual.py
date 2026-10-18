"""The manual weight-entry page.

The page exists so a weight can be typed before any hardware exists, and its whole
value depends on going through the real ingest pipeline rather than around it. So
these tests check the page renders the cylinder's own numbers (a wrong tare printed
on screen is how someone types 8 and wonders why it reads 0%), that an unregistered
device is told what to do about it, and that the payload the page actually sends is
accepted and stored as a real reading.
"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import Device, SensorReading
from app.services.manual_entry import (
    MANUAL_DEVICE_CODE,
    MANUAL_FIRMWARE,
    MANUAL_GAS_SENSOR_VALUE,
    MANUAL_WIFI_STATUS,
)

PAGE = "/manual"
INGEST = "/api/iot/sensor-data"


def page_payload(device_code: str, gross: float) -> dict:
    """Exactly what the page's fetch() sends - no timestamp, gas pinned to 0."""
    return {
        "device_id": device_code,
        "total_weight_kg": gross,
        "gas_sensor_value": MANUAL_GAS_SENSOR_VALUE,
        "wifi_status": MANUAL_WIFI_STATUS,
        "firmware_version": MANUAL_FIRMWARE,
    }


def _device(db, code: str) -> Device:
    return db.execute(
        select(Device).where(Device.device_code == code)
    ).scalar_one()


def test_page_renders_the_cylinders_own_numbers(client, cylinder):
    response = client.get(PAGE, params={"device": "ESP32-TEST-001"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    # The tare and capacity are what stop the gross-vs-net mistake, so they have to
    # come from this cylinder rather than being hardcoded in the template.
    assert "15.0" in body
    assert "14.2" in body
    assert "ESP32-TEST-001" in body
    assert cylinder.cylinder_code in body


def test_page_discloses_that_no_gas_is_measured(client, cylinder):
    body = client.get(PAGE, params={"device": "ESP32-TEST-001"}).text
    # Sending 0 cannot trip the leak threshold, but the dashboard still shows SAFE -
    # the absence of a measurement, not a safe measurement. The page must say so.
    assert "gas sensor value 0" in body
    assert "SAFE" in body


def test_unregistered_device_is_told_what_to_do(client, cylinder):
    response = client.get(PAGE, params={"device": "NOPE-001"})

    assert response.status_code == 404
    # The phone is nowhere near a terminal, so the page carries the command.
    assert "register_manual_device.py" in response.text
    assert "NOPE-001" in response.text


def test_default_device_is_the_manual_one(client, cylinder):
    """With no query parameter the page targets the phone device, which the test
    fixture does not create - so the 404 proves the default, not a lookup failure."""
    response = client.get(PAGE)

    assert response.status_code == 404
    assert MANUAL_DEVICE_CODE in response.text


def test_what_the_page_sends_is_accepted_and_stored_as_real(db, client, cylinder):
    db.add(
        Device(
            cylinder_id=cylinder.id,
            device_code=MANUAL_DEVICE_CODE,
            wifi_status="UNKNOWN",
            last_seen=None,
            firmware_version=MANUAL_FIRMWARE,
        )
    )
    db.flush()

    response = client.post(INGEST, json=page_payload(MANUAL_DEVICE_CODE, 23.4))
    assert response.status_code == 201

    body = response.json()
    assert body["gas_status"] == "SAFE"
    # Nothing typed may ever command the buzzer or the valve.
    assert body["safety_event_created"] is False
    assert body["buzzer_status"] == "OFF"

    reading = db.execute(
        select(SensorReading)
        .where(SensorReading.id == body["reading_id"])
    ).scalar_one()
    # A typed weight is a real observation, not demo data - it is honest about
    # being unmeasured via the device row, not by pretending to be simulated.
    assert reading.is_simulated is False
    assert reading.gas_sensor_value == MANUAL_GAS_SENSOR_VALUE


def test_typing_moves_only_the_phone_devices_last_seen(db, client, cylinder):
    esp = _device(db, "ESP32-TEST-001")
    # Whole seconds: the column is DATETIME with no fractional part, so MySQL would
    # round the stored value and the comparison below would fail on the rounding
    # rather than on anything the code did. The cylinder fixture does the same.
    esp.last_seen = (datetime.now() - timedelta(hours=3)).replace(microsecond=0)
    db.add(
        Device(
            cylinder_id=cylinder.id,
            device_code=MANUAL_DEVICE_CODE,
            wifi_status="UNKNOWN",
            last_seen=None,
            firmware_version=MANUAL_FIRMWARE,
        )
    )
    db.flush()
    esp_before = esp.last_seen

    assert client.post(INGEST, json=page_payload(MANUAL_DEVICE_CODE, 23.2)).status_code == 201
    db.expire_all()

    phone = _device(db, MANUAL_DEVICE_CODE)
    assert phone.last_seen is not None
    assert phone.wifi_status == MANUAL_WIFI_STATUS
    # The board has not reported; nothing about typing may suggest otherwise.
    assert _device(db, "ESP32-TEST-001").last_seen == esp_before


def test_the_phone_device_is_never_swept_offline(db, cylinder):
    """It is quiet between entries by definition. An alert telling the user to check
    power and WiFi on a device with neither is noise that teaches them to ignore the
    alert list."""
    from app.services import device_health

    db.add(
        Device(
            cylinder_id=cylinder.id,
            device_code=MANUAL_DEVICE_CODE,
            wifi_status=MANUAL_WIFI_STATUS,
            last_seen=datetime.now() - timedelta(days=2),
            firmware_version=MANUAL_FIRMWARE,
        )
    )
    db.flush()

    created = device_health.sweep(db, cylinder_ids=[cylinder.id])

    assert all(MANUAL_DEVICE_CODE not in alert.message for alert in created)
