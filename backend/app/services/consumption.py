"""Consumption from weight deltas, with the load cell's noise filtered out.

A load cell does not measure consumption; it measures weight, badly. Three things
have to be separated before a weight change means anything:

* **Noise.** The seeded walk carries +/-15 g of jitter and real hardware is worse.
  A delta under `MIN_MEANINGFUL_DELTA_KG` is discarded rather than accumulated,
  because summing jitter over 2,880 readings a day invents kilograms of
  consumption that never happened.
* **Refills.** Weight going *up* is not negative consumption. A positive jump of at
  least `REFILL_DELTA_KG` is classified as a refill and contributes nothing to the
  day's total.
* **Spikes.** A single wild sample (someone leaning on the cylinder) is suppressed
  by taking the rolling *median* of the last `SMOOTHING_WINDOW` readings rather
  than the mean, because one outlier cannot drag a median.

Both the delta and the refill test run on the *smoothed* series, not on raw
readings. That costs a little latency - a refill is confirmed once the median has
moved, which takes a few readings rather than being instant - and buys immunity to a
single spurious sample. For a safety product that trade is the right way round: a
38 kg spike from somebody leaning on the cylinder must never be recorded as a
delivery, and ~90 seconds at a 30-second interval is not a cost anyone notices.

The write side of consumption. The read side lives in `monitoring.py`.
"""

import statistics
from datetime import date
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ConsumptionRecord, SensorReading

# How a weight delta was classified.
NOISE = "NOISE"
CONSUMPTION = "CONSUMPTION"
REFILL = "REFILL"
IMPLAUSIBLE_DROP = "IMPLAUSIBLE_DROP"

ZERO = Decimal("0.000")


def smoothed_weight(weights: Sequence[Decimal]) -> Optional[Decimal]:
    """Rolling median of the most recent weights, newest-last.

    Median, not mean: a single spurious sample shifts a mean and barely moves a
    median, which is the whole reason for smoothing in the first place.
    """
    if not weights:
        return None
    window = list(weights)[-settings.smoothing_window :]
    return Decimal(statistics.median(window)).quantize(Decimal("0.001"))


def recent_weights(db: Session, cylinder_id: int, limit: Optional[int] = None) -> List[Decimal]:
    """The last N stored weights, oldest-first, ready for `smoothed_weight`."""
    limit = limit or settings.smoothing_window
    rows = db.execute(
        select(SensorReading.total_weight_kg)
        .where(SensorReading.cylinder_id == cylinder_id)
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
    ).scalars()
    return list(reversed(list(rows)))


def classify_delta(previous: Decimal, current: Decimal) -> Tuple[str, Decimal]:
    """Classify a smoothed weight change.

    Returns (kind, magnitude_kg) where magnitude is always non-negative.
    Weight falls as gas is burned, so `previous - current` is consumption.
    """
    delta = Decimal(previous) - Decimal(current)
    jump = Decimal(str(settings.refill_delta_kg))

    if -delta >= jump:
        # Weight went up by at least the refill threshold.
        return REFILL, -delta
    if delta >= jump:
        # Weight *fell* by more than a cylinder could burn in one interval. No
        # domestic burner uses 2 kg between readings, so this is a cylinder being
        # swapped, lifted off the scale, or a load-cell fault - not gas used.
        # Counting it would corrupt the daily average and with it the depletion
        # estimate, so it contributes nothing. The level on the dashboard still
        # follows the raw reading, so the user sees the lower level immediately.
        return IMPLAUSIBLE_DROP, delta.quantize(Decimal("0.001"))
    if abs(delta) < Decimal(str(settings.min_meaningful_delta_kg)):
        return NOISE, ZERO
    if delta < ZERO:
        # Rising, but by less than a refill: drift or a nudge, not gas appearing.
        return NOISE, ZERO
    return CONSUMPTION, delta.quantize(Decimal("0.001"))


def daily_average(db: Session, cylinder_id: int, exclude_today: bool = True) -> Decimal:
    """Mean daily consumption over the recorded days.

    Today is excluded by default because a partial day drags the average down and
    would make the depletion estimate optimistic right after midnight.
    """
    where = [ConsumptionRecord.cylinder_id == cylinder_id]
    if exclude_today:
        where.append(ConsumptionRecord.record_date < date.today())

    rows = db.execute(
        select(ConsumptionRecord.consumption_kg).where(*where)
    ).scalars().all()
    if not rows:
        return ZERO
    total = sum((Decimal(r) for r in rows), ZERO)
    return (total / Decimal(len(rows))).quantize(Decimal("0.001"))


def sample_count(db: Session, cylinder_id: int) -> int:
    """Complete days of history - what decides ML vs the arithmetic fallback."""
    return int(
        db.execute(
            select(func.count())
            .select_from(ConsumptionRecord)
            .where(
                ConsumptionRecord.cylinder_id == cylinder_id,
                ConsumptionRecord.record_date < date.today(),
            )
        ).scalar_one()
    )


def consumption_variance(db: Session, cylinder_id: int, days: int = 30) -> Decimal:
    """Population variance of recent daily consumption, used for confidence.

    A household whose daily use swings wildly cannot be predicted as confidently as
    a steady one, however many samples there are.
    """
    rows = db.execute(
        select(ConsumptionRecord.consumption_kg)
        .where(ConsumptionRecord.cylinder_id == cylinder_id)
        .order_by(ConsumptionRecord.record_date.desc())
        .limit(days)
    ).scalars().all()
    if len(rows) < 2:
        return ZERO
    return Decimal(statistics.pvariance([float(r) for r in rows])).quantize(
        Decimal("0.00001")
    )


def apply_delta(
    db: Session, cylinder_id: int, when: date, kind: str, magnitude: Decimal
) -> Optional[ConsumptionRecord]:
    """Add consumption to the day's record, creating it if needed.

    One row per cylinder per day is a database constraint
    (`uq_consumption_cyl_date`), so this reads-then-updates rather than inserting
    blindly. NOISE, REFILL and IMPLAUSIBLE_DROP deltas add nothing, but a row is
    still ensured for the day so a refill day is not a hole in the chart.
    """
    record = db.execute(
        select(ConsumptionRecord).where(
            ConsumptionRecord.cylinder_id == cylinder_id,
            ConsumptionRecord.record_date == when,
        )
    ).scalar_one_or_none()

    from datetime import datetime

    if record is None:
        record = ConsumptionRecord(
            cylinder_id=cylinder_id,
            record_date=when,
            timestamp=datetime.now(),
            consumption_kg=ZERO,
            daily_average_kg=ZERO,
        )
        db.add(record)
        db.flush()

    if kind == CONSUMPTION and magnitude > ZERO:
        record.consumption_kg = (Decimal(record.consumption_kg) + magnitude).quantize(
            Decimal("0.001")
        )
        record.timestamp = datetime.now()

    # Store the running average on the row, so every screen quotes the same number
    # the prediction was computed from.
    record.daily_average_kg = daily_average(db, cylinder_id, exclude_today=False)
    db.flush()
    return record
