"""The rule engine: smoothing, delta classification, the anomaly ladder, prediction.

Pure functions, no database. These are the tests that matter most, because every one
of them encodes a product rule that would otherwise only exist in a comment.
"""

from decimal import Decimal

import pytest

from app.services import anomaly
from app.ml import predictor
from app.services.consumption import (
    CONSUMPTION,
    NOISE,
    REFILL,
    classify_delta,
    smoothed_weight,
)


# --- smoothing -----------------------------------------------------------

def test_median_ignores_a_single_wild_sample():
    """Someone leaning on the cylinder must not move the smoothed weight."""
    steady = [Decimal("23.30"), Decimal("23.29"), Decimal("23.31"), Decimal("23.30")]
    with_spike = steady + [Decimal("58.00")]
    assert smoothed_weight(with_spike) == Decimal("23.300")


def test_smoothing_uses_only_the_window():
    """Old readings fall out, so the value tracks the present."""
    weights = [Decimal("30.0")] * 10 + [Decimal("20.0")] * 5
    assert smoothed_weight(weights) == Decimal("20.000")


def test_smoothed_weight_of_nothing_is_none():
    assert smoothed_weight([]) is None


# --- delta classification ------------------------------------------------

def test_small_change_is_noise_not_consumption():
    """15 g of load-cell jitter summed over 2,880 daily readings would invent kg."""
    kind, kg = classify_delta(Decimal("23.300"), Decimal("23.295"))
    assert kind == NOISE
    assert kg == Decimal("0.000")


def test_real_drop_is_consumption():
    kind, kg = classify_delta(Decimal("23.300"), Decimal("23.100"))
    assert kind == CONSUMPTION
    assert kg == Decimal("0.200")


def test_large_rise_is_a_refill_not_negative_consumption():
    kind, kg = classify_delta(Decimal("15.200"), Decimal("29.000"))
    assert kind == REFILL
    assert kg == Decimal("13.800")


def test_small_rise_is_noise_not_gas_appearing():
    """Gas does not appear. A sub-threshold rise is drift or a nudge."""
    kind, kg = classify_delta(Decimal("23.300"), Decimal("23.500"))
    assert kind == NOISE
    assert kg == Decimal("0.000")


def test_noise_floor_boundary_is_inclusive_of_consumption():
    """Exactly at MIN_MEANINGFUL_DELTA_KG (0.02) counts."""
    kind, _ = classify_delta(Decimal("23.300"), Decimal("23.280"))
    assert kind == CONSUMPTION


# --- the anomaly ladder (spec §22) ---------------------------------------

THRESHOLD = Decimal("60.00")
AVERAGE = Decimal("0.460")
GAS_LIMIT = 700


def _evaluate(today, gas):
    return anomaly.evaluate(
        today_kg=Decimal(today),
        average_kg=AVERAGE,
        anomaly_threshold_percent=THRESHOLD,
        gas_value=gas,
        gas_threshold=GAS_LIMIT,
    )


def test_normal_day_normal_air():
    assert _evaluate("0.470", 190).state == anomaly.NORMAL


def test_high_consumption_alone_never_escalates_past_unusual():
    """The rule this whole module exists for. Triple consumption, clean air."""
    verdict = _evaluate("1.500", 190)
    assert verdict.state == anomaly.UNUSUAL_CONSUMPTION
    assert verdict.is_leak is False


def test_absurd_consumption_alone_is_still_not_a_leak():
    verdict = _evaluate("99.000", 0)
    assert verdict.state == anomaly.UNUSUAL_CONSUMPTION
    assert verdict.is_leak is False


def test_gas_alone_is_a_possible_leak():
    verdict = _evaluate("0.470", 812)
    assert verdict.state == anomaly.POSSIBLE_LEAK
    assert verdict.is_leak is True


def test_gas_and_abnormal_consumption_together_are_critical():
    """Two independent signals agreeing is what earns CRITICAL."""
    assert _evaluate("1.500", 812).state == anomaly.CRITICAL_LEAK


def test_gas_threshold_boundary_is_inclusive():
    assert _evaluate("0.470", GAS_LIMIT).gas_exceeded is True
    assert _evaluate("0.470", GAS_LIMIT - 1).gas_exceeded is False


def test_anomaly_threshold_boundary_is_inclusive():
    """60% above a 0.460 average is 0.736 kg exactly."""
    assert _evaluate("0.736", 190).state == anomaly.UNUSUAL_CONSUMPTION
    assert _evaluate("0.735", 190).state == anomaly.NORMAL


def test_no_history_means_consumption_cannot_be_judged():
    verdict = anomaly.evaluate(
        today_kg=Decimal("5.000"),
        average_kg=Decimal("0.000"),
        anomaly_threshold_percent=THRESHOLD,
        gas_value=190,
        gas_threshold=GAS_LIMIT,
        has_history=False,
    )
    assert verdict.state == anomaly.NORMAL
    assert verdict.deviation_percent == Decimal("0")


def test_gas_is_still_judged_without_history():
    """A leak on day one is still a leak."""
    verdict = anomaly.evaluate(
        today_kg=Decimal("0.000"),
        average_kg=Decimal("0.000"),
        anomaly_threshold_percent=THRESHOLD,
        gas_value=900,
        gas_threshold=GAS_LIMIT,
        has_history=False,
    )
    assert verdict.state == anomaly.POSSIBLE_LEAK


def test_deviation_never_divides_by_zero():
    assert anomaly.deviation_percent(Decimal("1.0"), Decimal("0.0")) == Decimal("0")


def test_verdict_severity_ordering():
    assert _evaluate("1.500", 812).worse_than(anomaly.POSSIBLE_LEAK) is True
    assert _evaluate("0.470", 190).worse_than(anomaly.NORMAL) is False


# --- prediction ----------------------------------------------------------

def test_estimate_matches_the_seeded_arithmetic():
    est = predictor.estimate(Decimal("8.308"), Decimal("0.459"), sample_count=31)
    assert est.remaining_days == Decimal("18.10")
    assert est.method == predictor.FALLBACK
    assert est.is_estimate is True


def test_zero_average_does_not_divide_or_claim_infinite_days():
    est = predictor.estimate(Decimal("8.308"), Decimal("0.000"), sample_count=31)
    assert est.remaining_days == Decimal("0.00")
    assert est.predicted_depletion_date is None
    assert est.confidence == Decimal("0.000")


def test_near_zero_average_is_treated_as_not_consuming():
    """0.0001 kg/day would otherwise yield 83,080 days and overflow the column."""
    est = predictor.estimate(Decimal("8.308"), Decimal("0.0001"), sample_count=31)
    assert est.remaining_days == Decimal("0.00")
    assert est.predicted_depletion_date is None


def test_remaining_days_fits_the_decimal_6_2_column():
    est = predictor.estimate(Decimal("14.200"), Decimal("0.001"), sample_count=31)
    assert est.remaining_days <= Decimal("9999.99")


def test_empty_cylinder_is_zero_days_not_negative():
    est = predictor.estimate(Decimal("-5.000"), Decimal("0.459"), sample_count=31)
    assert est.remaining_kg == Decimal("0.000")
    assert est.remaining_days == Decimal("0.00")


def test_confidence_grows_with_history():
    low = predictor.estimate(Decimal("8.0"), Decimal("0.46"), sample_count=3).confidence
    high = predictor.estimate(Decimal("8.0"), Decimal("0.46"), sample_count=30).confidence
    assert high > low


def test_confidence_shrinks_with_volatility():
    steady = predictor.confidence_from(30, Decimal("0.000"))
    erratic = predictor.confidence_from(30, Decimal("0.060"))
    assert erratic < steady


def test_confidence_is_capped_well_below_certainty():
    """This is division, not a model. It must not present itself as one."""
    assert predictor.confidence_from(10_000, Decimal("0")) <= Decimal("0.55")


def test_confidence_never_negative():
    assert predictor.confidence_from(1, Decimal("99")) >= Decimal("0")


def test_no_samples_is_no_confidence():
    assert predictor.confidence_from(0, Decimal("0")) == Decimal("0")


@pytest.mark.parametrize("samples,expected", [(13, False), (14, True), (31, True)])
def test_ml_sample_threshold(samples, expected):
    assert predictor.uses_model(samples) is expected


# --- implausible drops ---------------------------------------------------

def test_huge_sudden_drop_is_not_consumption():
    """A cylinder swapped for an emptier one is not 6 kg of gas burned.

    Counting it would corrupt the daily average and with it every depletion estimate
    that follows.
    """
    from app.services.consumption import IMPLAUSIBLE_DROP

    kind, kg = classify_delta(Decimal("23.000"), Decimal("17.000"))
    assert kind == IMPLAUSIBLE_DROP
    assert kg == Decimal("6.000")


def test_the_jump_threshold_is_symmetric():
    """One constant governs both directions: 2 kg up is a refill, 2 kg down is not gas."""
    from app.services.consumption import IMPLAUSIBLE_DROP

    assert classify_delta(Decimal("23.000"), Decimal("21.000"))[0] == IMPLAUSIBLE_DROP
    assert classify_delta(Decimal("21.000"), Decimal("23.000"))[0] == REFILL


def test_a_large_but_plausible_burn_still_counts():
    """Just under the threshold is still real consumption."""
    kind, kg = classify_delta(Decimal("23.000"), Decimal("21.100"))
    assert kind == CONSUMPTION
    assert kg == Decimal("1.900")
