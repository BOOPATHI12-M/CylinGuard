"""The model path, the fallback boundary, and the refill recommendation.

The tests that matter here are the ones that stop the product overstating itself: that
`method` reports what actually ran, that confidence is earned rather than granted, and that
every failure mode lands on the arithmetic path instead of taking a request down.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import settings
from app.ml import features as feature_builder
from app.ml import model as model_store
from app.ml import predictor
from app.services import refill


def day(offset: int) -> date:
    return date(2026, 9, 1) + timedelta(days=offset)


def synthetic_history(days: int, daily: float = 0.46) -> list:
    """A steady household, with a weekday pattern the model can actually learn."""
    records = []
    remaining = 13.0
    for index in range(days):
        current = day(index)
        # Heavier at weekends: a real signal, so a model that beats the mean is beating it
        # for a reason rather than by memorising noise.
        used = daily * (1.4 if current.weekday() >= 5 else 0.85)
        remaining = max(0.0, remaining - used)
        records.append(
            feature_builder.DayRecord(day=current, consumption_kg=used, remaining_kg=remaining)
        )
    return records


@pytest.fixture(autouse=True)
def no_leftover_artifact():
    """Each test starts with no model on disk, and leaves none behind."""
    model_store.delete()
    yield
    model_store.delete()


# --- features ------------------------------------------------------------

def test_feature_row_has_the_seven_spec_features():
    history = synthetic_history(10)
    row = feature_builder.build_row(history[:-1], 8.26, day(9))
    assert len(row) == len(feature_builder.FEATURE_NAMES) == 7


def test_dataset_leaves_room_for_history():
    """A 31-day history yields 28 rows: the first three have nothing behind them."""
    features, targets = feature_builder.build_dataset(synthetic_history(31))
    assert len(features) == len(targets) == 31 - feature_builder.MIN_HISTORY_DAYS


def test_features_do_not_leak_the_target():
    """The remaining-gas feature must be the *previous* day's close, not today's.

    Using today's close would leak today's consumption into the features predicting it.
    """
    history = synthetic_history(6)
    features, _ = feature_builder.build_dataset(history)
    first_row = features[0]
    opening = history[feature_builder.MIN_HISTORY_DAYS - 1].remaining_kg
    assert first_row[0] == pytest.approx(opening)
    # Explicitly *not* the same day's closing level.
    assert first_row[0] != pytest.approx(history[feature_builder.MIN_HISTORY_DAYS].remaining_kg)


def test_features_survive_a_single_day_of_history():
    row = feature_builder.build_row(synthetic_history(1), 13.0, day(1))
    assert all(isinstance(value, float) for value in row)


# --- training ------------------------------------------------------------

def test_training_refuses_too_little_history():
    """A forest will fit five points and report zero error - the most misleading result
    it could produce, so it is not attempted."""
    features, targets = feature_builder.build_dataset(synthetic_history(10))
    model, report = model_store.train(features, targets)
    assert model is None and report is None


def test_training_succeeds_with_enough_history():
    features, targets = feature_builder.build_dataset(synthetic_history(40))
    model, report = model_store.train(features, targets)

    assert model is not None
    assert report.sample_count == len(features)
    assert report.feature_names == list(feature_builder.FEATURE_NAMES)
    assert report.folds >= 2, "error must be cross-validated, not in-sample"
    assert report.model_mae >= 0 and report.baseline_mae > 0


def test_the_report_states_the_baseline_it_must_beat():
    """MAE alone is unreadable; MAE against predicting the mean is the honest claim."""
    features, targets = feature_builder.build_dataset(synthetic_history(60))
    _, report = model_store.train(features, targets)
    assert report.baseline_mae > 0
    assert isinstance(report.beats_baseline, bool)


def test_a_learnable_pattern_is_actually_learned():
    """With a real weekday signal the model should beat a flat average."""
    features, targets = feature_builder.build_dataset(synthetic_history(90))
    _, report = model_store.train(features, targets)
    assert report.beats_baseline, (
        f"model MAE {report.model_mae} did not beat baseline {report.baseline_mae}"
    )


def test_save_and_load_round_trip():
    features, targets = feature_builder.build_dataset(synthetic_history(40))
    model, report = model_store.train(features, targets)
    model_store.save(model, report)

    loaded, loaded_report = model_store.load()
    assert loaded is not None
    assert loaded_report["sample_count"] == report.sample_count

    row = feature_builder.build_row(synthetic_history(40), 8.26, day(41))
    assert model_store.predict_daily_consumption(loaded, row) >= 0


def test_load_returns_nothing_when_untrained():
    assert model_store.load() == (None, None)


def test_a_model_with_mismatched_features_is_refused(monkeypatch):
    """A model fitted on a different feature order would return confident nonsense."""
    features, targets = feature_builder.build_dataset(synthetic_history(40))
    model, report = model_store.train(features, targets)
    report.feature_names = ["something", "else", "entirely"]
    model_store.save(model, report)

    assert model_store.load() == (None, None)


def test_a_corrupt_artifact_does_not_raise():
    """A bad artifact must not take the API down; the arithmetic path still works."""
    path = model_store.artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a joblib file")
    assert model_store.load() == (None, None)


def test_prediction_is_never_negative():
    """A cylinder cannot gain gas."""
    features, targets = feature_builder.build_dataset(synthetic_history(40))
    model, _ = model_store.train(features, targets)
    # A nonsense row, to make sure the floor is the code's and not the data's.
    assert model_store.predict_daily_consumption(model, [-99, -99, -99, -99, -99, -99, 0]) >= 0


# --- the estimate contract ----------------------------------------------

def test_model_path_reports_ML_and_is_not_an_estimate():
    result = predictor.estimate_from_daily(
        Decimal("8.26"), Decimal("0.46"), sample_count=31, model_mae=0.05, baseline_mae=0.12
    )
    assert result.method == predictor.ML
    assert result.is_estimate is False
    assert result.remaining_days == Decimal("17.96")


def test_fallback_path_still_reports_FALLBACK():
    result = predictor.estimate(Decimal("8.26"), Decimal("0.46"), sample_count=31)
    assert result.method == predictor.FALLBACK
    assert result.is_estimate is True


def test_both_paths_agree_when_the_model_predicts_the_average():
    """The final division is identical; only the denominator's origin differs."""
    arithmetic = predictor.estimate(Decimal("8.26"), Decimal("0.46"), sample_count=31)
    modelled = predictor.estimate_from_daily(
        Decimal("8.26"), Decimal("0.46"), sample_count=31, model_mae=0.05, baseline_mae=0.12
    )
    assert arithmetic.remaining_days == modelled.remaining_days


def test_model_path_guards_the_division_too():
    """A near-zero forecast must not produce infinite days."""
    result = predictor.estimate_from_daily(
        Decimal("8.26"), Decimal("0.0001"), sample_count=31, model_mae=0.05, baseline_mae=0.12
    )
    assert result.remaining_days == Decimal("0.00")
    assert result.predicted_depletion_date is None


def test_model_path_fits_the_decimal_column():
    result = predictor.estimate_from_daily(
        Decimal("14.2"), Decimal("0.001"), sample_count=31, model_mae=0.05, baseline_mae=0.12
    )
    assert result.remaining_days <= Decimal("9999.99")


# --- confidence is earned, not granted ----------------------------------

def test_a_model_that_barely_beats_the_mean_earns_barely_more_confidence():
    fallback_ceiling = Decimal("0.55")
    barely = predictor.confidence_from_model(31, model_mae=0.119, baseline_mae=0.12)
    assert fallback_ceiling <= barely <= Decimal("0.60")


def test_a_much_better_model_earns_much_more():
    barely = predictor.confidence_from_model(31, model_mae=0.119, baseline_mae=0.12)
    strong = predictor.confidence_from_model(31, model_mae=0.02, baseline_mae=0.12)
    assert strong > barely


def test_a_model_worse_than_the_mean_earns_no_bonus():
    """Running a forest is not itself evidence of anything."""
    worse = predictor.confidence_from_model(31, model_mae=0.30, baseline_mae=0.12)
    assert worse == Decimal("0.550")


def test_confidence_is_capped_below_certainty():
    perfect = predictor.confidence_from_model(31, model_mae=0.0, baseline_mae=0.12)
    assert perfect <= Decimal("0.90")


def test_missing_metrics_claim_no_more_than_the_fallback():
    assert predictor.confidence_from_model(31, None, None) == Decimal("0.550")


@pytest.mark.parametrize("samples,expected", [(13, False), (14, True), (31, True)])
def test_the_sample_boundary_is_unchanged(samples, expected):
    assert predictor.uses_model(samples) is expected
    assert settings.ml_min_samples == 14


# --- refill recommendation ----------------------------------------------

def test_plenty_of_gas_needs_no_refill():
    result = refill.recommend(Decimal("58.2"), Decimal("17.9"), threshold_days=5)
    assert result.urgency == refill.NOT_NEEDED
    assert result.should_refill is False


def test_approaching_the_threshold_says_plan_ahead():
    result = refill.recommend(Decimal("30"), Decimal("9"), threshold_days=5)
    assert result.urgency == refill.PLAN_AHEAD
    assert result.should_refill is False


def test_at_the_threshold_says_order_now():
    result = refill.recommend(Decimal("18"), Decimal("5"), threshold_days=5)
    assert result.urgency == refill.ORDER_NOW
    assert result.should_refill is True


def test_a_nearly_empty_cylinder_is_urgent_whatever_the_day_count():
    """At 4% a cylinder can run out mid-use even if the average suggests a week."""
    result = refill.recommend(Decimal("4"), Decimal("20"), threshold_days=5)
    assert result.urgency == refill.URGENT
    assert result.should_refill is True


def test_no_prediction_is_reported_as_such_not_as_fine():
    result = refill.recommend(Decimal("58"), None, threshold_days=5)
    assert result.urgency == refill.NOT_NEEDED
    assert result.days_remaining is None
    assert "No depletion estimate yet" in result.reason


def test_every_recommendation_explains_itself():
    for percentage, days in [("58.2", "17.9"), ("30", "9"), ("18", "5"), ("4", "20")]:
        result = refill.recommend(Decimal(percentage), Decimal(days), threshold_days=5)
        assert len(result.reason) > 20
        # No ordering integration exists, so nothing may imply one.
        assert "order placed" not in result.reason.lower()


# --- a model that loses to the mean must not be used --------------------

def test_a_model_worse_than_the_mean_is_not_used():
    """Running a forest is not evidence. On steady consumption the flat average genuinely
    is the better predictor, and preferring the model would make the forecast worse while
    labelling it POWERED BY ML."""
    from app.services.prediction import _beats_baseline

    assert _beats_baseline({"model_mae": 0.05, "baseline_mae": 0.03}) is False
    assert _beats_baseline({"model_mae": 0.03, "baseline_mae": 0.05}) is True


def test_an_unproven_model_is_not_used():
    """Missing metrics count as not beating it: an unproven model should not displace the
    path whose behaviour we know."""
    from app.services.prediction import _beats_baseline

    assert _beats_baseline(None) is False
    assert _beats_baseline({}) is False
    assert _beats_baseline({"model_mae": 0.03}) is False
    assert _beats_baseline({"model_mae": 0.03, "baseline_mae": 0}) is False


def test_status_separates_trained_from_in_use(monkeypatch):
    """"Trained but idle" is a real state the API has to be able to express."""
    from app.services import prediction as prediction_service

    features, targets = feature_builder.build_dataset(synthetic_history(40))
    model, report = model_store.train(features, targets)
    # Force the stored metrics to say the model lost.
    report.model_mae = 0.50
    report.baseline_mae = 0.10
    model_store.save(model, report)

    status = prediction_service.model_status()
    assert status["trained"] is True
    assert status["in_use"] is False
    assert status["beats_baseline"] is False
