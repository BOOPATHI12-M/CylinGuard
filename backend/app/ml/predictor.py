"""Depletion estimate.

Phase 2b implements only the arithmetic path:

    days_remaining = remaining_kg / average_daily_consumption

Phase 6 adds a RandomForest behind the same signature. The contract that the
frontend binds to - `remaining_days`, `predicted_depletion_date`, `confidence`,
`method` - is identical either way, so the model drops in without a frontend change.

Three things this is careful about, because a prediction is the easiest place in the
product to lie:

* **The division is guarded.** A near-zero daily average would otherwise produce
  infinity, and `remaining_days` is a NOT NULL DECIMAL(6,2) that cannot hold it.
* **Confidence is derived, not invented.** It comes from how many complete days of
  history exist and how steady they are. A household that burns 0.2 kg one day and
  1.4 kg the next is genuinely less predictable, and the number says so.
* **`method` reports what actually computed the answer.** Below
  `ML_MIN_SAMPLES` complete days there is no model, so it returns FALLBACK and the
  UI shows ESTIMATE. It never claims a model that has not run.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from app.config import settings

FALLBACK = "FALLBACK"
ML = "ML"

ZERO = Decimal("0")
# remaining_days is DECIMAL(6,2): 9999.99 is the largest value the column holds.
MAX_DAYS = Decimal("9999.99")
# Beyond ~10 years a depletion date is noise, and date arithmetic starts to overflow.
MAX_DATE_DAYS = 3650
# Below this the average is indistinguishable from "not consuming", and dividing by
# it produces a meaningless number rather than a large one.
MIN_USABLE_AVERAGE = Decimal("0.001")


@dataclass
class Estimate:
    remaining_kg: Decimal
    remaining_days: Decimal
    predicted_depletion_date: Optional[date]
    confidence: Decimal
    method: str
    sample_count: int

    @property
    def is_estimate(self) -> bool:
        return self.method != ML


def confidence_from(sample_count: int, variance: Decimal) -> Decimal:
    """Confidence in 0..1 for the arithmetic path.

    Grows with history and shrinks with volatility, and is deliberately capped well
    below certainty: this is division, not a model, and it should never present
    itself as one. The ceiling is what the ML path has to beat to be worth having.
    """
    if sample_count <= 0:
        return ZERO

    # 0 samples -> 0.00, 14 samples -> ~0.29, 40+ -> 0.55 ceiling.
    from_samples = min(Decimal("0.55"), Decimal("0.15") + Decimal("0.01") * sample_count)

    # Penalise instability. A variance of 0.05 kg^2 on a ~0.46 kg/day household is
    # already a lot of swing, so the penalty bites early.
    penalty = min(Decimal("0.30"), Decimal(variance) * Decimal("4"))

    return max(ZERO, (from_samples - penalty)).quantize(Decimal("0.001"))


def estimate(
    remaining_kg: Decimal,
    average_daily_kg: Decimal,
    sample_count: int,
    variance: Decimal = ZERO,
    now: Optional[datetime] = None,
) -> Estimate:
    """Arithmetic depletion estimate. Always returns a usable, in-range answer."""
    now = now or datetime.now()
    remaining = max(ZERO, Decimal(remaining_kg))
    average = Decimal(average_daily_kg)

    if average < MIN_USABLE_AVERAGE:
        # Not consuming, or not enough signal to say. Reporting 0 days with zero
        # confidence is honest; reporting "infinite days left" is not.
        return Estimate(
            remaining_kg=remaining.quantize(Decimal("0.001")),
            remaining_days=ZERO.quantize(Decimal("0.01")),
            predicted_depletion_date=None,
            confidence=ZERO.quantize(Decimal("0.001")),
            method=FALLBACK,
            sample_count=sample_count,
        )

    days = min(MAX_DAYS, (remaining / average)).quantize(Decimal("0.01"))
    depletion = (now + timedelta(days=float(min(days, Decimal(MAX_DATE_DAYS))))).date()

    return Estimate(
        remaining_kg=remaining.quantize(Decimal("0.001")),
        remaining_days=days,
        predicted_depletion_date=depletion,
        confidence=confidence_from(sample_count, variance),
        # The model lands in phase 6. Until it has actually run, this is an estimate
        # and says so.
        method=FALLBACK,
        sample_count=sample_count,
    )


def confidence_from_model(
    sample_count: int, model_mae: Optional[float], baseline_mae: Optional[float]
) -> Decimal:
    """Confidence for the model path, from how much it actually beats the flat average.

    Not a fixed, higher number just because a model ran. A forest that barely improves on
    predicting the mean has earned barely more confidence than the arithmetic path, and
    one that is *worse* than the mean earns less. The metrics come from the training
    report, so this is measured rather than asserted.
    """
    if sample_count <= 0:
        return ZERO

    # Starts where the arithmetic path tops out, so the model can only improve on it.
    base = Decimal("0.55")

    if not model_mae or not baseline_mae or baseline_mae <= 0:
        # Trained, but with no usable comparison - claim no more than the fallback would.
        return base.quantize(Decimal("0.001"))

    # 1.0 means the model is perfect, 0.0 means no better than the mean, negative means
    # worse. Clamped, then scaled into the headroom above 0.55.
    improvement = max(0.0, min(1.0, 1.0 - (float(model_mae) / float(baseline_mae))))
    earned = base + (Decimal("0.90") - base) * Decimal(f"{improvement:.4f}")
    return earned.quantize(Decimal("0.001"))


def estimate_from_daily(
    remaining_kg: Decimal,
    predicted_daily_kg: Decimal,
    sample_count: int,
    variance: Decimal = ZERO,
    method: str = ML,
    model_mae: Optional[float] = None,
    baseline_mae: Optional[float] = None,
    now: Optional[datetime] = None,
) -> Estimate:
    """Days remaining from a *predicted* daily consumption rather than the historical mean.

    The final division is identical to the arithmetic path, and so are its guards: a
    near-zero prediction cannot produce infinite days, and the result still fits
    DECIMAL(6,2). Only the denominator differs - a model's forecast instead of a flat
    average.
    """
    now = now or datetime.now()
    remaining = max(ZERO, Decimal(remaining_kg))
    daily = Decimal(predicted_daily_kg)

    if daily < MIN_USABLE_AVERAGE:
        # The model predicts effectively no consumption. Reporting 0 days with zero
        # confidence is honest; "infinite days left" is not.
        return Estimate(
            remaining_kg=remaining.quantize(Decimal("0.001")),
            remaining_days=ZERO.quantize(Decimal("0.01")),
            predicted_depletion_date=None,
            confidence=ZERO.quantize(Decimal("0.001")),
            method=method,
            sample_count=sample_count,
        )

    days = min(MAX_DAYS, (remaining / daily)).quantize(Decimal("0.01"))
    depletion = (now + timedelta(days=float(min(days, Decimal(MAX_DATE_DAYS))))).date()

    return Estimate(
        remaining_kg=remaining.quantize(Decimal("0.001")),
        remaining_days=days,
        predicted_depletion_date=depletion,
        confidence=confidence_from_model(sample_count, model_mae, baseline_mae),
        method=method,
        sample_count=sample_count,
    )


def uses_model(sample_count: int) -> bool:
    """Whether there is enough history for the trained model to be used at all."""
    return sample_count >= settings.ml_min_samples
