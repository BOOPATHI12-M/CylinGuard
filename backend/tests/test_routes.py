"""The read endpoints, and the ownership rule that guards all of them."""

from tests.conftest import TEST_PASSWORD, make_cylinder, make_user


# --- ownership (spec §34) -------------------------------------------------

def test_another_users_cylinder_is_404_not_403(client, db, cylinder, auth):
    """404, so the response cannot confirm that someone else's cylinder exists."""
    stranger = make_user(db, "stranger@test.local", "Stranger")
    theirs = make_cylinder(db, stranger, "CYL-STRANGER-001")

    for path in (
        f"/api/dashboard/{theirs.id}",
        f"/api/consumption/{theirs.id}",
        f"/api/prediction/{theirs.id}",
        f"/api/safety/{theirs.id}",
        f"/api/history/{theirs.id}",
        f"/api/alerts/{theirs.id}",
        f"/api/settings/{theirs.id}",
    ):
        assert client.get(path, headers=auth).status_code == 404, path


def test_every_cylinder_route_requires_a_token(client, cylinder):
    for path in (
        f"/api/dashboard/{cylinder.id}",
        f"/api/consumption/{cylinder.id}",
        f"/api/history/{cylinder.id}",
        f"/api/settings/{cylinder.id}",
    ):
        assert client.get(path).status_code == 401, path


def test_cannot_mark_another_users_alert_read(client, db, cylinder, auth):
    from app.models import Alert, AlertSeverity

    stranger = make_user(db, "stranger2@test.local")
    theirs = make_cylinder(db, stranger, "CYL-STRANGER-002")
    alert = Alert(
        cylinder_id=theirs.id,
        type="LOW_LPG",
        severity=AlertSeverity.INFO,
        message="Not yours",
        is_read=False,
    )
    db.add(alert)
    db.flush()

    assert client.post(f"/api/alerts/{alert.id}/read", headers=auth).status_code == 404
    assert alert.is_read is False


# --- dashboard -----------------------------------------------------------

def test_dashboard_returns_the_derived_numbers(client, cylinder, auth):
    body = client.get(f"/api/dashboard/{cylinder.id}", headers=auth).json()

    # Newest reading is 23.200 kg against a 15.000 kg tare and 14.200 kg capacity.
    assert body["lpg"]["remaining_kg"] == 8.2
    assert body["lpg"]["percentage"] == 57.7
    assert body["lpg"]["status"] == "NORMAL"
    assert body["lpg"]["is_simulated"] is True
    assert body["gas"]["status"] == "SAFE"
    assert body["gas"]["exceeded"] is False
    assert body["device"]["status"] == "ONLINE"
    assert body["unread_alerts"] == 1
    # No prediction row was seeded for this cylinder, and none is invented.
    assert body["prediction"] is None


def test_dashboard_without_readings_is_409_not_zeros(client, db, owner, auth):
    """Inventing zeros would put a number on screen that no sensor produced."""
    bare = make_cylinder(db, owner, "CYL-NO-READINGS")
    response = client.get(f"/api/dashboard/{bare.id}", headers=auth)
    assert response.status_code == 409


def test_offline_device_is_derived_not_stored(client, db, cylinder, auth):
    from datetime import datetime, timedelta

    from app.models import Device

    device = db.query(Device).filter(Device.cylinder_id == cylinder.id).one()
    device.last_seen = datetime.now() - timedelta(hours=2)
    db.flush()

    body = client.get(f"/api/dashboard/{cylinder.id}", headers=auth).json()
    assert body["device"]["status"] == "OFFLINE"


# --- history pagination --------------------------------------------------

def test_history_paginates_in_sql(client, cylinder, auth):
    page1 = client.get(f"/api/history/{cylinder.id}?page=1&size=4", headers=auth).json()
    assert page1["total"] == 10
    assert page1["size"] == 4
    assert page1["pages"] == 3
    assert len(page1["items"]) == 4

    page3 = client.get(f"/api/history/{cylinder.id}?page=3&size=4", headers=auth).json()
    assert len(page3["items"]) == 2  # 10 rows over pages of 4

    ids = {r["id"] for r in page1["items"]} & {r["id"] for r in page3["items"]}
    assert not ids, "pages must not overlap"


def test_history_is_newest_first_and_carries_derived_fields(client, cylinder, auth):
    items = client.get(f"/api/history/{cylinder.id}?size=10", headers=auth).json()["items"]
    stamps = [r["timestamp"] for r in items]
    assert stamps == sorted(stamps, reverse=True)
    assert items[0]["remaining_kg"] == 8.2
    assert items[0]["gas_status"] == "SAFE"


def test_history_rejects_an_oversized_page(client, cylinder, auth):
    assert client.get(f"/api/history/{cylinder.id}?size=500", headers=auth).status_code == 422


# --- safety --------------------------------------------------------------

def test_safety_reports_recorded_actuator_state(client, cylinder, auth):
    """Buzzer and relay come from the recorded event, never inferred from gas."""
    body = client.get(f"/api/safety/{cylinder.id}", headers=auth).json()

    # The fixture holds a leak that was later cleared. The endpoint must report the
    # state of the *latest* event, and still list the incident in history.
    assert body["gas"]["status"] == "SAFE"
    assert body["buzzer_status"] == "OFF"
    assert body["relay_status"] == "NORMAL"
    assert body["events"][0]["event_type"] == "CLEARED"
    assert [e["event_type"] for e in body["events"]] == ["CLEARED", "LEAK_SUSPECTED"]


# --- alerts --------------------------------------------------------------

def test_mark_alert_read_and_count_drops(client, db, cylinder, auth):
    listing = client.get(f"/api/alerts/{cylinder.id}", headers=auth).json()
    assert listing["unread_count"] == 1
    alert_id = listing["items"][0]["id"]

    marked = client.post(f"/api/alerts/{alert_id}/read", headers=auth)
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    after = client.get(f"/api/alerts/{cylinder.id}", headers=auth).json()
    assert after["unread_count"] == 0


def test_alerts_reject_an_unknown_severity(client, cylinder, auth):
    response = client.get(f"/api/alerts/{cylinder.id}?severity=URGENT", headers=auth)
    assert response.status_code == 422


# --- settings ------------------------------------------------------------

def test_settings_round_trip(client, cylinder, auth):
    response = client.put(
        f"/api/settings/{cylinder.id}",
        headers=auth,
        json={"gas_leakage_threshold": 650, "low_lpg_threshold": 25},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gas_leakage_threshold"] == 650
    assert body["low_lpg_threshold"] == 25.0
    # Untouched fields keep their values.
    assert body["critical_lpg_threshold"] == 10.0


def test_settings_rejects_critical_above_low(client, cylinder, auth):
    response = client.put(
        f"/api/settings/{cylinder.id}", headers=auth, json={"critical_lpg_threshold": 30}
    )
    assert response.status_code == 422
    assert "critical_lpg_threshold" in response.text


def test_settings_rejects_a_zero_gas_threshold(client, cylinder, auth):
    """Mirrors the ck_settings_gas CHECK, so the caller gets 422 not a 503."""
    response = client.put(
        f"/api/settings/{cylinder.id}", headers=auth, json={"gas_leakage_threshold": 0}
    )
    assert response.status_code == 422


def test_settings_rejects_an_empty_update(client, cylinder, auth):
    assert client.put(f"/api/settings/{cylinder.id}", headers=auth, json={}).status_code == 422


def test_settings_cannot_write_anything_secret(client, cylinder, auth):
    """Unknown fields are ignored, so the Settings page cannot reach a secret."""
    response = client.put(
        f"/api/settings/{cylinder.id}",
        headers=auth,
        json={"gas_leakage_threshold": 700, "jwt_secret": "pwned", "password_hash": "x"},
    )
    assert response.status_code == 200
    assert "jwt_secret" not in response.text


# --- GET /api/cylinders (phase 5) ----------------------------------------

def test_lists_only_my_cylinders(client, db, cylinder, auth):
    """Added in phase 5: without this the shell had a hardcoded cylinder id."""
    stranger = make_user(db, "cyl-stranger@test.local")
    make_cylinder(db, stranger, "CYL-NOT-MINE")

    body = client.get("/api/cylinders", headers=auth).json()
    codes = [row["cylinder_code"] for row in body]
    assert "CYL-TEST-001" in codes
    assert "CYL-NOT-MINE" not in codes


def test_cylinder_summary_carries_derived_level(client, cylinder, auth):
    row = next(
        r
        for r in client.get("/api/cylinders", headers=auth).json()
        if r["cylinder_code"] == "CYL-TEST-001"
    )
    assert row["remaining_kg"] == 8.2
    assert row["percentage"] == 57.7
    assert row["status"] == "NORMAL"
    assert row["has_readings"] is True
    assert row["device_status"] == "ONLINE"


def test_a_cylinder_with_no_readings_reports_null_not_zero(client, db, owner, auth):
    """0% would read as an empty cylinder; null lets the UI say "no data"."""
    make_cylinder(db, owner, "CYL-SILENT")

    row = next(
        r
        for r in client.get("/api/cylinders", headers=auth).json()
        if r["cylinder_code"] == "CYL-SILENT"
    )
    assert row["has_readings"] is False
    assert row["remaining_kg"] is None
    assert row["percentage"] is None
    assert row["status"] is None


def test_listing_cylinders_requires_a_token(client):
    assert client.get("/api/cylinders").status_code == 401


def test_dashboard_carries_the_thresholds_and_commanded_state(client, cylinder, auth):
    """Phase 5 additions, so the banner and refill card need no second request."""
    body = client.get(f"/api/dashboard/{cylinder.id}", headers=auth).json()

    assert body["refill_threshold_days"] == 5
    assert body["low_lpg_threshold"] == 20.0
    assert body["critical_lpg_threshold"] == 10.0
    # The fixture's latest safety event is the CLEARED one.
    assert body["buzzer_status"] == "OFF"
    assert body["relay_status"] == "NORMAL"
