"""Test fixtures.

`Base.metadata.create_all()` is deliberately never used, here or anywhere:
`database/schema.sql` is the single source of DDL truth, and a schema generated
from the models would be a different schema (see decision 4 in
memory/PROJECT_STATE.md and scripts/check_schema_parity.py).

Isolation instead comes from running every test inside a transaction that is always
rolled back. The session joins the outer transaction with
`join_transaction_mode="create_savepoint"`, so application code is free to call
`commit()` - that releases a savepoint rather than committing, and the outer
rollback still discards everything. Tests therefore exercise the real MySQL schema,
with real CHECK constraints and real cascades, without being able to leave a row
behind.

This also avoids needing a second database: `cylinguard_user` is granted on
`cylinguard` only, so it cannot CREATE DATABASE for a scratch copy.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import (
    Alert,
    AlertSeverity,
    Cylinder,
    Device,
    SafetyEvent,
    SensorReading,
    Setting,
    User,
)
from app.security.passwords import hash_password

TEST_PASSWORD = "test-password-123"


@pytest.fixture(scope="session")
def connection():
    conn = engine.connect()
    yield conn
    conn.close()


@pytest.fixture
def db(connection) -> Session:
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()


@pytest.fixture
def client(db) -> TestClient:
    """A client whose requests share the test's rolled-back session.

    TestClient is built without its context manager on purpose, so the app's
    lifespan does not run: it would dispose the very engine this test's connection
    was checked out from.
    """
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_user(db: Session, email: str, name: str = "Test User") -> User:
    user = User(name=name, email=email, password_hash=hash_password(TEST_PASSWORD))
    db.add(user)
    db.flush()
    return user


def make_cylinder(db: Session, user: User, code: str) -> Cylinder:
    cylinder = Cylinder(
        user_id=user.id,
        cylinder_code=code,
        empty_weight_kg=Decimal("15.000"),
        capacity_kg=Decimal("14.200"),
    )
    db.add(cylinder)
    db.flush()
    db.add(
        Setting(
            cylinder_id=cylinder.id,
            low_lpg_threshold=Decimal("20.00"),
            critical_lpg_threshold=Decimal("10.00"),
            gas_leakage_threshold=700,
        )
    )
    db.flush()
    return cylinder


@pytest.fixture
def owner(db) -> User:
    return make_user(db, "owner@test.local", "Owner")


@pytest.fixture
def cylinder(db, owner) -> Cylinder:
    """A cylinder with a device, 10 readings, an alert and a safety event."""
    cyl = make_cylinder(db, owner, "CYL-TEST-001")
    now = datetime.now().replace(microsecond=0)

    db.add(
        Device(
            cylinder_id=cyl.id,
            device_code="ESP32-TEST-001",
            wifi_status="CONNECTED",
            last_seen=now,
            firmware_version="1.0.0",
        )
    )
    # 23.2 kg total -> 8.2 kg of gas -> 57.7% of a 14.2 kg capacity.
    for i in range(10):
        db.add(
            SensorReading(
                cylinder_id=cyl.id,
                timestamp=now - timedelta(minutes=15 * (9 - i)),
                total_weight_kg=Decimal("23.200") + Decimal("0.010") * (9 - i),
                gas_sensor_value=190,
                device_status="ONLINE",
                is_simulated=True,
            )
        )
    db.add(
        Alert(
            cylinder_id=cyl.id,
            type="LOW_LPG",
            severity=AlertSeverity.WARNING,
            message="Test alert",
            is_read=False,
        )
    )
    db.add(
        SafetyEvent(
            cylinder_id=cyl.id,
            gas_value=812,
            threshold=700,
            buzzer_status="ON",
            relay_status="ACTIVATED",
            event_type="LEAK_SUSPECTED",
        )
    )
    db.flush()
    return cyl


@pytest.fixture
def auth(client, owner) -> dict:
    """Authorization header for `owner`, obtained through the real login route."""
    response = client.post(
        "/api/auth/login",
        json={"email": owner.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
