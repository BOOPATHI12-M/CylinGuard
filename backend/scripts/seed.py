"""Populate CylinGuard with realistic demo data.

Generates ~30 days of sensor history for one user / one cylinder / one ESP32,
including a mid-period refill, derived daily consumption, predictions, alerts
and one past safety event, so the dashboard is populated immediately after
setup.

The walk is deliberately *gradual*: cooking draws LPG in small bursts during
meal windows, and the load cell adds a little noise. No implausible jumps.

Usage:
    python scripts/seed.py            # seed if empty
    python scripts/seed.py --reset    # wipe CylinGuard tables first
"""

import argparse
import math
import pathlib
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from _dbguard import guarded  # noqa: E402
from app.database import session_scope  # noqa: E402
from app.models import (  # noqa: E402
    Alert,
    AlertSeverity,
    ConsumptionRecord,
    Cylinder,
    Device,
    Prediction,
    SafetyEvent,
    SensorReading,
    Setting,
    User,
)
from app.security.passwords import hash_password  # noqa: E402

# --- Demo account -------------------------------------------------------
DEMO_EMAIL = "demo@cylinguard.local"
DEMO_PASSWORD = "cylinguard123"
DEMO_NAME = "Demo User"

CYLINDER_CODE = "CYL-DOM-001"
DEVICE_CODE = "ESP32-CYL-001"
EMPTY_WEIGHT = Decimal("15.000")
CAPACITY = Decimal("14.200")

DAYS_OF_HISTORY = 30
READING_INTERVAL_MINUTES = 15
# Meal windows (hour, typical kg burned across that window)
MEAL_WINDOWS = [(7, 0.14), (12, 0.18), (19, 0.22)]
BASELINE_GAS = 180          # clean-air MQ-6 ADC baseline
GAS_LEAK_THRESHOLD = 700
# A past gas incident, as an offset back from `now`. The *readings* carry the raised
# values across this window and the safety events sit on its edges, so the Safety page's
# event log and the History page's "gas over threshold" filter agree with each other.
# Seeding the events alone left a leak that no reading could corroborate - exactly the
# cross-page inconsistency a demo exposes.
LEAK_FROM_HOURS_AGO = 9 * 24 + 6
LEAK_TO_HOURS_AGO = 9 * 24 + 5
LEAK_GAS = 812
CLEARING_GAS = 240

# Tables owned by CylinGuard, ordered child -> parent for safe truncation.
OWNED_TABLES = [
    "sensor_readings",
    "consumption_records",
    "predictions",
    "alerts",
    "safety_events",
    "settings",
    "devices",
    "cylinders",
    "users",
]

rng = random.Random(20261005)  # deterministic: the demo looks the same every run


def reset_tables(db) -> None:
    db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in OWNED_TABLES:
        db.execute(text(f"TRUNCATE TABLE {table}"))
    db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    print(f"Reset {len(OWNED_TABLES)} tables")


def meal_burn(ts: datetime) -> float:
    """kg consumed in the interval ending at ts, from overlapping meal windows."""
    total = 0.0
    for hour, kg in MEAL_WINDOWS:
        # A ~90-minute bell curve around each meal hour.
        delta_minutes = (ts.hour - hour) * 60 + ts.minute
        weight = math.exp(-((delta_minutes / 45.0) ** 2))
        if weight > 0.01:
            share = READING_INTERVAL_MINUTES / 90.0
            total += kg * weight * share * rng.uniform(0.75, 1.25)
    return total


def generate_readings(cylinder_id: int, now: datetime):
    """Yield (SensorReading, true_weight) walking backwards-to-forwards in time."""
    start = (now - timedelta(days=DAYS_OF_HISTORY)).replace(
        minute=0, second=0, microsecond=0
    )
    # Start a little below a full cylinder so there is history on both sides.
    true_weight = float(EMPTY_WEIGHT) + float(CAPACITY) * 0.62
    refill_at = start + timedelta(days=18)
    refilled = False

    ts = start
    while ts <= now:
        if not refilled and ts >= refill_at:
            # A refill is a single large positive step - the consumption
            # engine must classify this as a refill, not negative usage.
            true_weight = float(EMPTY_WEIGHT) + float(CAPACITY) * 0.985
            refilled = True
        else:
            true_weight = max(float(EMPTY_WEIGHT), true_weight - meal_burn(ts))

        # Load-cell noise: +/- ~15 g, the thing the smoother has to absorb.
        measured = true_weight + rng.gauss(0, 0.015)
        hours_ago = (now - ts).total_seconds() / 3600
        if LEAK_TO_HOURS_AGO <= hours_ago <= LEAK_FROM_HOURS_AGO:
            # Inside the seeded incident: readings genuinely show gas above the threshold.
            gas = max(0, int(rng.gauss(LEAK_GAS, 25)))
        else:
            gas = max(0, int(rng.gauss(BASELINE_GAS, 18)))

        yield SensorReading(
            cylinder_id=cylinder_id,
            timestamp=ts,
            total_weight_kg=Decimal(f"{max(0.0, measured):.3f}"),
            gas_sensor_value=gas,
            device_status="ONLINE",
            is_simulated=True,
        ), true_weight, refilled

        ts += timedelta(minutes=READING_INTERVAL_MINUTES)


def build_daily_consumption(readings) -> dict[date, float]:
    """Daily kg consumed, derived from true weight and ignoring refill steps."""
    per_day: dict[date, float] = {}
    previous = None
    for reading, true_weight, _ in readings:
        if previous is not None:
            delta = previous - true_weight
            if delta > 0:  # positive delta = consumption; refills are negative
                per_day[reading.timestamp.date()] = (
                    per_day.get(reading.timestamp.date(), 0.0) + delta
                )
        previous = true_weight
    return per_day


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="truncate tables first")
    args = parser.parse_args()

    now = datetime.now().replace(second=0, microsecond=0)

    with session_scope() as db:
        if args.reset:
            reset_tables(db)

        if db.query(User).filter(User.email == DEMO_EMAIL).first():
            print(
                f"Demo user {DEMO_EMAIL} already exists - nothing to do. "
                "Re-run with --reset to regenerate."
            )
            return 0

        # --- user / cylinder / device / settings ---
        user = User(
            name=DEMO_NAME,
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.flush()

        cylinder = Cylinder(
            user_id=user.id,
            cylinder_code=CYLINDER_CODE,
            empty_weight_kg=EMPTY_WEIGHT,
            capacity_kg=CAPACITY,
        )
        db.add(cylinder)
        db.flush()

        db.add(
            Device(
                cylinder_id=cylinder.id,
                device_code=DEVICE_CODE,
                wifi_status="CONNECTED",
                last_seen=now,
                firmware_version="1.0.0",
            )
        )
        db.add(
            Setting(
                cylinder_id=cylinder.id,
                gas_leakage_threshold=GAS_LEAK_THRESHOLD,
                # measurement_interval is deliberately left at the schema
                # default (30s, the live device cadence). READING_INTERVAL_MINUTES
                # is only how coarsely this script backfills synthetic history -
                # writing it here would tell the device to report every 15
                # minutes, which would bound leak-detection latency at 15 min.
                demo_mode=True,
            )
        )

        # --- sensor readings ---
        readings = list(generate_readings(cylinder.id, now))
        db.bulk_save_objects([r for r, _, _ in readings])
        print(f"Inserted {len(readings)} sensor readings")

        # --- daily consumption ---
        per_day = build_daily_consumption(readings)
        ordered_days = sorted(per_day)
        running: list[float] = []
        for day in ordered_days:
            kg = per_day[day]
            running.append(kg)
            db.add(
                ConsumptionRecord(
                    cylinder_id=cylinder.id,
                    record_date=day,
                    timestamp=datetime.combine(day, datetime.min.time())
                    + timedelta(hours=23, minutes=59),
                    consumption_kg=Decimal(f"{kg:.3f}"),
                    daily_average_kg=Decimal(f"{sum(running) / len(running):.3f}"),
                )
            )
        print(f"Inserted {len(ordered_days)} daily consumption records")

        # --- predictions (one per day for the last week) ---
        # Each row is the estimate as it would have stood on its own day, so the
        # prediction chart shows a real downward trend rather than a flat line.
        # method is FALLBACK, not ML: no model has been trained at this point, and
        # claiming otherwise would make the dashboard assert something untrue.
        weight_at = sorted((r.timestamp, true_w) for r, true_w, _ in readings)
        for offset in range(7, 0, -1):
            ts = now - timedelta(days=offset - 1)
            true_weight = next(
                (w for t, w in reversed(weight_at) if t <= ts), weight_at[0][1]
            )
            remaining = max(0.0, true_weight - float(EMPTY_WEIGHT))
            # average over the days that had actually elapsed by `ts`
            elapsed = [kg for day, kg in per_day.items() if day <= ts.date()]
            avg = sum(elapsed) / len(elapsed) if elapsed else 0.0
            days_left = min(remaining / avg, 9999.0) if avg > 0 else 0.0
            depletion = (
                (ts + timedelta(days=min(days_left, 3650.0))).date() if avg > 0 else None
            )
            db.add(
                Prediction(
                    cylinder_id=cylinder.id,
                    timestamp=ts,
                    remaining_kg=Decimal(f"{remaining:.3f}"),
                    remaining_days=Decimal(f"{days_left:.2f}"),
                    predicted_depletion_date=depletion,
                    # Modest, derived from how much history backs it. Phase 2b owns
                    # the real formula; this only has to be honest, not clever.
                    confidence=Decimal(f"{min(0.55, 0.15 + 0.01 * len(elapsed)):.3f}"),
                    method="FALLBACK",
                    sample_count=len(elapsed),
                )
            )
        print("Inserted 7 predictions")

        # --- alerts ---
        refill_day = next(
            (r.timestamp for r, _, did in readings if did), now - timedelta(days=12)
        )
        # Measure the refill rather than quoting a literal: the alert text is a
        # number a user reads, and the product rule is that no displayed figure is
        # invented. Largest positive step between consecutive true weights.
        refill_kg = max(
            (b - a for (_, a, _), (_, b, _) in zip(readings, readings[1:])),
            default=0.0,
        )
        db.add_all(
            [
                Alert(
                    cylinder_id=cylinder.id,
                    type="REFILL_DETECTED",
                    severity=AlertSeverity.INFO,
                    message=(
                        f"Cylinder refill detected - weight increased by {refill_kg:.2f} kg."
                    ),
                    is_read=True,
                    created_at=refill_day,
                ),
                Alert(
                    cylinder_id=cylinder.id,
                    type="ABNORMAL_CONSUMPTION",
                    severity=AlertSeverity.WARNING,
                    message=(
                        "Consumption higher than normal (1.12 kg vs 0.54 kg average). "
                        "Check for an unattended burner or regulator fault."
                    ),
                    is_read=False,
                    created_at=now - timedelta(days=4, hours=3),
                ),
                Alert(
                    cylinder_id=cylinder.id,
                    type="GAS_THRESHOLD_EXCEEDED",
                    severity=AlertSeverity.CRITICAL,
                    message=(
                        "MQ-6 reading 812 exceeded the configured threshold of 700. "
                        "Buzzer activated. Investigate before resuming use."
                    ),
                    is_read=True,
                    created_at=now - timedelta(days=9, hours=6),
                ),
                Alert(
                    cylinder_id=cylinder.id,
                    type="LOW_LPG",
                    severity=AlertSeverity.WARNING,
                    message="LPG level below 20% of capacity. Plan a refill.",
                    is_read=False,
                    created_at=now - timedelta(hours=8),
                ),
            ]
        )

        # --- safety events ---
        db.add_all(
            [
                SafetyEvent(
                    cylinder_id=cylinder.id,
                    gas_value=LEAK_GAS,
                    threshold=GAS_LEAK_THRESHOLD,
                    buzzer_status="ON",
                    relay_status="ACTIVATED",
                    event_type="LEAK_SUSPECTED",
                    created_at=now - timedelta(hours=LEAK_FROM_HOURS_AGO),
                ),
                SafetyEvent(
                    cylinder_id=cylinder.id,
                    gas_value=CLEARING_GAS,
                    threshold=GAS_LEAK_THRESHOLD,
                    buzzer_status="OFF",
                    relay_status="NORMAL",
                    event_type="CLEARED",
                    created_at=now - timedelta(hours=LEAK_TO_HOURS_AGO),
                ),
            ]
        )

        final_remaining = max(0.0, readings[-1][1] - float(EMPTY_WEIGHT))
        print(
            "\nSeed complete.\n"
            f"  Login : {DEMO_EMAIL}\n"
            f"  Pass  : {DEMO_PASSWORD}\n"
            f"  Device: {DEVICE_CODE}\n"
            f"  Remaining LPG: {final_remaining:.2f} kg "
            f"({final_remaining / float(CAPACITY) * 100:.1f}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(guarded(main))
