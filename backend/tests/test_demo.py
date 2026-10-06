"""Demo simulator and device-offline detection.

The two rules worth protecting here:

* a genuine ESP32 packet suspends simulation for that cylinder, so invented readings
  never compete with real hardware;
* a device that goes quiet raises **one** alert per episode, not one per sweep.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Alert, Device, SensorReading
from app.services import demo_state, device_health, simulator
from app.services.consumption import IMPLAUSIBLE_DROP


@pytest.fixture(autouse=True)
def clean_demo_state():
    """The registry is process-global, so each test starts from nothing."""
    demo_state.reset()
    yield
    demo_state.reset()


def _alerts_of(db, cylinder_id, alert_type) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Alert)
            .where(Alert.cylinder_id == cylinder_id, Alert.type == alert_type)
        ).scalar_one()
    )


# --- the walk is plausible ----------------------------------------------

def test_each_step_stays_inside_the_plausible_band():
    """Above the 0.02 kg noise floor so it registers; far below the 2 kg jump
    threshold so it is never read as a refill or a cylinder change."""
    empty = Decimal("15.000")
    current = Decimal("29.000")
    now = datetime(2026, 10, 6, 12, 0)

    for _ in range(300):
        nxt = simulator.next_weight(current, empty, now)
        step = abs(current - nxt)
        assert step < Decimal("2.0"), f"implausible jump of {step} kg"
        current = nxt
    assert current >= empty


def test_the_walk_never_goes_below_the_empty_cylinder():
    """A cylinder cannot weigh less than its own steel."""
    empty = Decimal("15.000")
    current = Decimal("15.010")
    for _ in range(50):
        current = simulator.next_weight(current, empty, datetime.now())
    assert current >= empty


def test_meal_times_draw_more_than_the_small_hours():
    assert simulator.meal_weighting(datetime(2026, 10, 6, 19, 0)) > simulator.meal_weighting(
        datetime(2026, 10, 6, 3, 0)
    )


# --- real hardware wins -------------------------------------------------

def test_a_real_packet_suspends_simulation(client, db, cylinder):
    assert demo_state.state_for(cylinder.id).suspended is False

    response = client.post(
        "/api/iot/sensor-data",
        json={
            "device_id": "ESP32-TEST-001",
            "total_weight_kg": 23.100,
            "gas_sensor_value": 190,
        },
    )
    assert response.status_code == 201
    assert demo_state.state_for(cylinder.id).suspended is True
    assert demo_state.state_for(cylinder.id).suspended_at is not None


def test_a_suspended_cylinder_is_not_simulated(db, cylinder):
    assert any(c.id == cylinder.id for c, _, _ in simulator.eligible_cylinders(db))
    demo_state.note_real_packet(cylinder.id)
    assert not any(c.id == cylinder.id for c, _, _ in simulator.eligible_cylinders(db))


def test_simulated_readings_are_flagged_as_such(db, cylinder):
    """`is_simulated` is the whole basis for telling demo data from a measurement."""
    from app.services import ingest

    _, device, setting = next(
        (c, d, s) for c, d, s in simulator.eligible_cylinders(db) if c.id == cylinder.id
    )
    packet = simulator.build_packet(db, cylinder, device, setting)
    outcome = ingest.process(db, packet, simulated=True)
    assert outcome.reading.is_simulated is True


def test_enabling_demo_mode_clears_a_suspension(client, db, cylinder, auth):
    demo_state.note_real_packet(cylinder.id)
    assert demo_state.state_for(cylinder.id).suspended is True

    response = client.post(
        f"/api/demo/{cylinder.id}/toggle", headers=auth, json={"enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["suspended_by_real_device"] is False


def test_disabling_demo_mode_removes_the_cylinder_from_the_simulator(
    client, db, cylinder, auth
):
    client.post(f"/api/demo/{cylinder.id}/toggle", headers=auth, json={"enabled": False})
    assert not any(c.id == cylinder.id for c, _, _ in simulator.eligible_cylinders(db))


# --- scenarios -----------------------------------------------------------

def test_scenario_round_trip(client, cylinder, auth):
    response = client.post(
        f"/api/demo/{cylinder.id}/scenario", headers=auth, json={"scenario": "leak_detected"}
    )
    assert response.status_code == 200
    assert response.json()["scenario"] == "LEAK_DETECTED"


def test_unknown_scenario_is_rejected(client, cylinder, auth):
    response = client.post(
        f"/api/demo/{cylinder.id}/scenario", headers=auth, json={"scenario": "EXPLODE"}
    )
    assert response.status_code == 422


def test_leak_scenario_pushes_gas_above_the_threshold(db, cylinder):
    _, device, setting = next(
        (c, d, s) for c, d, s in simulator.eligible_cylinders(db) if c.id == cylinder.id
    )
    demo_state.set_scenario(cylinder.id, demo_state.LEAK_DETECTED)
    packet = simulator.build_packet(db, cylinder, device, setting)
    assert packet.gas_sensor_value > setting.gas_leakage_threshold


def test_normal_scenario_keeps_gas_in_clean_air(db, cylinder):
    _, device, setting = next(
        (c, d, s) for c, d, s in simulator.eligible_cylinders(db) if c.id == cylinder.id
    )
    for _ in range(30):
        packet = simulator.build_packet(db, cylinder, device, setting)
        assert packet.gas_sensor_value < setting.gas_leakage_threshold


def test_low_scenario_parks_just_under_the_low_threshold(db, cylinder):
    from app.services import lpg

    _, device, setting = next(
        (c, d, s) for c, d, s in simulator.eligible_cylinders(db) if c.id == cylinder.id
    )
    demo_state.set_scenario(cylinder.id, demo_state.LOW_LPG)
    packet = simulator.build_packet(db, cylinder, device, setting)

    remaining = lpg.remaining_kg(
        Decimal(f"{packet.total_weight_kg:.3f}"), cylinder.empty_weight_kg
    )
    percent = lpg.percentage(remaining, cylinder.capacity_kg)
    assert percent < setting.low_lpg_threshold
    assert lpg.level_status(percent, setting.low_lpg_threshold, setting.critical_lpg_threshold) in (
        lpg.LOW,
        lpg.CRITICAL,
    )


def test_low_scenario_drop_is_not_counted_as_consumption(db, cylinder):
    """The one-off level change is large, so the pipeline must refuse to bank it."""
    from app.services import consumption, ingest

    _, device, setting = next(
        (c, d, s) for c, d, s in simulator.eligible_cylinders(db) if c.id == cylinder.id
    )
    demo_state.set_scenario(cylinder.id, demo_state.LOW_LPG)

    before = db.execute(
        select(func.coalesce(func.sum(consumption.ConsumptionRecord.consumption_kg), 0)).where(
            consumption.ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()

    # Several ticks, so the smoothed series actually moves to the new level.
    kinds = []
    for _ in range(5):
        packet = simulator.build_packet(db, cylinder, device, setting)
        kinds.append(ingest.process(db, packet, simulated=True).delta_kind)
        demo_state.note_tick(cylinder.id)

    after = db.execute(
        select(func.coalesce(func.sum(consumption.ConsumptionRecord.consumption_kg), 0)).where(
            consumption.ConsumptionRecord.cylinder_id == cylinder.id
        )
    ).scalar_one()

    assert IMPLAUSIBLE_DROP in kinds, kinds
    # Ordinary per-tick consumption may still be banked; the multi-kg scenario drop
    # must not be.
    assert Decimal(after) - Decimal(before) < Decimal("1.0")


# --- device offline (spec §33) ------------------------------------------

def _go_quiet(db, cylinder_id, seconds=3600) -> Device:
    device = db.execute(
        select(Device).where(Device.cylinder_id == cylinder_id)
    ).scalar_one()
    device.last_seen = datetime.now() - timedelta(seconds=seconds)
    db.flush()
    return device


def _sweep(db, cylinder, **kwargs):
    """Sweep scoped to this test's cylinder.

    The real sweep is deliberately global - it has to find every quiet device - and
    the live database also holds the seeded demo cylinder, whose device stopped
    reporting when seeding finished.
    """
    return device_health.sweep(db, cylinder_ids=[cylinder.id], **kwargs)


def test_a_quiet_device_raises_one_alert(db, cylinder):
    _go_quiet(db, cylinder.id)
    created = _sweep(db, cylinder)
    assert len(created) == 1
    assert created[0].type == "DEVICE_OFFLINE"
    assert created[0].severity.value == "WARNING"


def test_repeated_sweeps_do_not_re_alert(db, cylinder):
    """At a 30s sweep, an overnight outage would otherwise raise 1,440 warnings."""
    _go_quiet(db, cylinder.id)
    _sweep(db, cylinder)
    for _ in range(5):
        assert _sweep(db, cylinder) == []
    assert _alerts_of(db, cylinder.id, "DEVICE_OFFLINE") == 1


def test_a_live_device_is_not_flagged(db, cylinder):
    assert _sweep(db, cylinder) == []


def test_offline_alert_does_not_claim_the_readings_are_current(db, cylinder):
    _go_quiet(db, cylinder.id)
    alert = _sweep(db, cylinder)[0]
    assert "not current" in alert.message


def test_wifi_status_is_marked_unknown_not_disconnected(db, cylinder):
    """We cannot see the device's radio, only its silence."""
    device = _go_quiet(db, cylinder.id)
    _sweep(db, cylinder)
    assert device.wifi_status == "UNKNOWN"


def test_a_new_episode_alerts_again(client, db, cylinder):
    """Alerting is per episode: quiet, back, quiet again is two alerts.

    The second outage is simulated by moving `now` forward rather than pushing
    `last_seen` back. Rewinding would place last_seen *before* the first alert, which
    is not what a later outage looks like - time only runs one way.
    """
    _go_quiet(db, cylinder.id)
    _sweep(db, cylinder)
    assert _alerts_of(db, cylinder.id, "DEVICE_OFFLINE") == 1

    # The device reports again, moving last_seen past the first alert.
    client.post(
        "/api/iot/sensor-data",
        json={
            "device_id": "ESP32-TEST-001",
            "total_weight_kg": 23.050,
            "gas_sensor_value": 190,
        },
    )

    # An hour later it has gone quiet again.
    later = datetime.now() + timedelta(hours=1)
    assert len(_sweep(db, cylinder, now=later)) == 1
    assert _alerts_of(db, cylinder.id, "DEVICE_OFFLINE") == 2


def test_coming_back_online_is_announced_once(client, db, cylinder):
    _go_quiet(db, cylinder.id)
    response = client.post(
        "/api/iot/sensor-data",
        json={
            "device_id": "ESP32-TEST-001",
            "total_weight_kg": 23.050,
            "gas_sensor_value": 190,
        },
    )
    assert response.status_code == 201
    assert _alerts_of(db, cylinder.id, "DEVICE_ONLINE") == 1

    # A second packet from an already-online device must not repeat it.
    client.post(
        "/api/iot/sensor-data",
        json={
            "device_id": "ESP32-TEST-001",
            "total_weight_kg": 23.040,
            "gas_sensor_value": 190,
        },
    )
    assert _alerts_of(db, cylinder.id, "DEVICE_ONLINE") == 1


def test_a_device_that_never_reported_alerts_once(db, owner):
    from tests.conftest import make_cylinder

    fresh = make_cylinder(db, owner, "CYL-NEVER-SEEN")
    db.add(Device(cylinder_id=fresh.id, device_code="ESP32-NEVER", last_seen=None))
    db.flush()

    assert len(device_health.sweep(db, cylinder_ids=[fresh.id])) == 1
    assert device_health.sweep(db, cylinder_ids=[fresh.id]) == []


# --- the state endpoint -------------------------------------------------

def test_demo_state_reports_both_switches(client, cylinder, auth):
    body = client.get(f"/api/demo/{cylinder.id}", headers=auth).json()
    assert body["demo_mode"] is True
    assert body["scenario"] == "NORMAL"
    assert body["available_scenarios"] == ["NORMAL", "LOW_LPG", "LEAK_DETECTED"]
    # The background loop is off by default, and the response says so rather than
    # leaving a dashboard wondering why nothing moves.
    assert body["simulator_running"] is False


def test_demo_routes_require_ownership(client, db, cylinder, auth):
    from tests.conftest import make_cylinder, make_user

    stranger = make_user(db, "demo-stranger@test.local")
    theirs = make_cylinder(db, stranger, "CYL-DEMO-STRANGER")

    assert client.get(f"/api/demo/{theirs.id}", headers=auth).status_code == 404
    assert (
        client.post(
            f"/api/demo/{theirs.id}/toggle", headers=auth, json={"enabled": False}
        ).status_code
        == 404
    )


def test_demo_routes_require_a_token(client, cylinder):
    assert client.get(f"/api/demo/{cylinder.id}").status_code == 401
