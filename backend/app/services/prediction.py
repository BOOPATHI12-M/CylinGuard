"""Produce a depletion estimate, by model where possible and by arithmetic otherwise.

This is the one place that decides which path ran, and `method` on the stored row is set
from what actually happened - not from what was configured, not from what was hoped. Three
things make the model path unavailable, and any one of them silently returns the
arithmetic estimate:

* fewer than `ML_MIN_SAMPLES` complete days of history;
* no persisted artifact (nobody has trained yet);
* an artifact that fails to load, or was fitted on a different feature order.

The frontend badge reads `method`, so a cylinder with a trained model shows POWERED BY ML
and one without shows ESTIMATE, with no frontend change between them. That is the whole
reason phase 2b built the fallback behind this contract.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.ml import features as feature_builder
from app.ml import model as model_store
from app.ml import predictor
from app.models import ConsumptionRecord, SensorReading
from app.services import consumption as consumption_service

logger = logging.getLogger("cylinguard.prediction")


def _beats_baseline(report: Optional[dict]) -> bool:
    """Whether the stored metrics show the model improving on a flat average.

    A report without usable metrics counts as *not* beating it: an unproven model should
    not displace the path we know the behaviour of.
    """
    if not report:
        return False
    model_mae = report.get("model_mae")
    baseline_mae = report.get("baseline_mae")
    if model_mae is None or not baseline_mae:
        return False
    return float(model_mae) < float(baseline_mae)


def daily_history(db: Session, cylinder_id: int, days: int = 120) -> List[feature_builder.DayRecord]:
    """Per-day consumption paired with the level at the end of that day.

    The closing level comes from the last reading of each day rather than from
    `consumption_records`, which does not store it. Two queries rather than a correlated
    subquery per day.
    """
    records = list(
        db.execute(
            select(ConsumptionRecord)
            .where(ConsumptionRecord.cylinder_id == cylinder_id)
            .order_by(ConsumptionRecord.record_date.desc())
            .limit(days)
        ).scalars()
    )
    if not records:
        return []

    earliest = min(record.record_date for record in records)

    # Last reading per day: MySQL has no DISTINCT ON, so take the max timestamp per date
    # and join back to it.
    day_column = func.date(SensorReading.timestamp)
    latest_per_day = (
        select(day_column.label("day"), func.max(SensorReading.timestamp).label("at"))
        .where(
            SensorReading.cylinder_id == cylinder_id,
            SensorReading.timestamp >= datetime.combine(earliest, datetime.min.time()),
        )
        .group_by(day_column)
        .subquery()
    )
    closing = {
        row.day if isinstance(row.day, date) else date.fromisoformat(str(row.day)): float(row.total_weight_kg)
        for row in db.execute(
            select(SensorReading.timestamp, SensorReading.total_weight_kg, latest_per_day.c.day)
            .join(latest_per_day, SensorReading.timestamp == latest_per_day.c.at)
            .where(SensorReading.cylinder_id == cylinder_id)
        )
    }

    history: List[feature_builder.DayRecord] = []
    for record in sorted(records, key=lambda item: item.record_date):
        total_weight = closing.get(record.record_date)
        if total_weight is None:
            # A consumption row with no reading that day cannot contribute a level, and a
            # guessed one would feed the model a number nobody measured.
            continue
        history.append(
            feature_builder.DayRecord(
                day=record.record_date,
                consumption_kg=float(record.consumption_kg),
                # Gas remaining, not gross weight - the feature is about the gas.
                remaining_kg=total_weight,
            )
        )
    return history


def _to_remaining(history: List[feature_builder.DayRecord], empty_weight: float):
    """Convert stored gross weights into gas remaining, floored at zero."""
    return [
        feature_builder.DayRecord(
            day=record.day,
            consumption_kg=record.consumption_kg,
            remaining_kg=max(0.0, record.remaining_kg - empty_weight),
        )
        for record in history
    ]


def compute(
    db: Session,
    cylinder_id: int,
    remaining_kg: Decimal,
    empty_weight_kg: Decimal,
    average_daily_kg: Decimal,
    sample_count: int,
    variance: Decimal,
    now: Optional[datetime] = None,
) -> predictor.Estimate:
    """The estimate for this cylinder, by whichever path is actually available."""
    now = now or datetime.now()

    if sample_count < settings.ml_min_samples:
        # Not enough history. Deliberate, and the UI says ESTIMATE.
        return predictor.estimate(remaining_kg, average_daily_kg, sample_count, variance, now)

    model, report = model_store.load()
    if model is None:
        return predictor.estimate(remaining_kg, average_daily_kg, sample_count, variance, now)

    # A model that cross-validates *worse* than predicting the historical mean must not be
    # used. Running a forest is not itself evidence of anything: on steady consumption the
    # flat average genuinely is the better predictor, and preferring the model would make
    # the forecast worse while labelling it POWERED BY ML. The artifact is kept and the
    # metrics stay visible on /api/ml/status so the operator can see why it is idle.
    if not _beats_baseline(report):
        logger.info(
            "model is not better than the mean (MAE %s vs baseline %s) - using arithmetic",
            report.get("model_mae"),
            report.get("baseline_mae"),
        )
        return predictor.estimate(remaining_kg, average_daily_kg, sample_count, variance, now)

    history = _to_remaining(daily_history(db, cylinder_id), float(empty_weight_kg))
    if len(history) < feature_builder.MIN_HISTORY_DAYS:
        return predictor.estimate(remaining_kg, average_daily_kg, sample_count, variance, now)

    try:
        row = feature_builder.build_row(history, float(remaining_kg), now.date())
        predicted_daily = model_store.predict_daily_consumption(model, row)
    except Exception:
        # A prediction failure must never take an ingest request down - the arithmetic
        # path is always available.
        logger.exception("model prediction failed for cylinder=%s", cylinder_id)
        return predictor.estimate(remaining_kg, average_daily_kg, sample_count, variance, now)

    return predictor.estimate_from_daily(
        remaining_kg=remaining_kg,
        predicted_daily_kg=Decimal(f"{predicted_daily:.4f}"),
        sample_count=sample_count,
        variance=variance,
        method=predictor.ML,
        model_mae=report.get("model_mae"),
        baseline_mae=report.get("baseline_mae"),
        now=now,
    )


def train_cylinder(db: Session, cylinder_id: int, empty_weight_kg: Decimal):
    """Fit and persist a model from this cylinder's history.

    Returns the report, or None when there is not enough history. One model is kept for
    the deployment rather than one per cylinder: a household has one or two, and a
    per-cylinder artifact would mean the first cylinder's model silently serving the
    second. Revisit if multi-cylinder fleets arrive.
    """
    history = _to_remaining(daily_history(db, cylinder_id), float(empty_weight_kg))
    features, targets = feature_builder.build_dataset(history)

    model, report = model_store.train(features, targets)
    if model is None:
        return None
    model_store.save(model, report)
    return report


def model_status() -> dict:
    """What the API reports about the current artifact."""
    model, report = model_store.load()
    return {
        "trained": model is not None,
        # Trained is not the same as in use: a model that loses to the mean is kept for
        # inspection but not used, and the UI keeps showing ESTIMATE.
        "in_use": model is not None and _beats_baseline(report),
        "beats_baseline": _beats_baseline(report),
        "artifact_path": str(model_store.artifact_path()),
        "min_samples_required": settings.ml_min_samples,
        "report": report or None,
    }
