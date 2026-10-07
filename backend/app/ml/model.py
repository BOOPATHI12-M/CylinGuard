"""Fitting, persisting and loading the RandomForest.

Three things this module is deliberate about.

**It reports fit, not forecast quality.** A 31-day history yields 28 training rows. That is
a small set, and cross-validated error on 28 rows of synthetic data says almost nothing
about how the model would do on a real household. `train` therefore returns the model's
error *and the error of simply predicting the historical mean*, so the only honest claim -
"it beats the flat average by this much on this data" - is the one the numbers support.

**It refuses to train on too little.** Below `ML_MIN_SAMPLES` days there is no attempt; the
caller keeps the arithmetic path. A RandomForest will happily fit five points and report
zero training error, which is the most misleading thing it could do.

**The artifact carries its own metadata.** Feature order, sample count, metrics and the
training timestamp are saved beside the estimator, so a loaded model can be checked against
the feature names the code now builds. A model fitted on a different feature order would
otherwise produce confident nonsense.
"""

import logging
import pathlib
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, cross_val_score

from app.config import settings
from app.ml.features import FEATURE_NAMES

logger = logging.getLogger("cylinguard.ml")

# Small and shallow on purpose: with tens of rows, a deep unconstrained forest memorises
# the training set. These bounds keep it a smoother than the flat mean rather than an
# interpolator of noise.
N_ESTIMATORS = 200
MAX_DEPTH = 6
MIN_SAMPLES_LEAF = 2
RANDOM_STATE = 42


@dataclass
class TrainingReport:
    trained_at: str
    sample_count: int
    feature_names: List[str]
    # Mean absolute error in kg/day, cross-validated where there are enough rows.
    model_mae: float
    # MAE of predicting the historical mean every day. The number the model has to beat.
    baseline_mae: float
    folds: int
    feature_importances: dict

    @property
    def beats_baseline(self) -> bool:
        return self.model_mae < self.baseline_mae


def artifact_path() -> pathlib.Path:
    """Resolved against the backend directory, so it works from any working directory."""
    configured = pathlib.Path(settings.ml_model_path)
    if configured.is_absolute():
        return configured
    return pathlib.Path(__file__).resolve().parents[2] / configured


def _baseline_mae(targets: Sequence[float]) -> float:
    """Error from always predicting the mean - the comparison that makes MAE meaningful.

    `len(...) == 0` rather than `not targets`: this is called with a numpy array, and
    truth-testing an array of more than one element raises.
    """
    values = np.asarray(targets, dtype=float)
    if values.size == 0:
        return 0.0
    return float(np.mean(np.abs(values - values.mean())))


def train(
    features: Sequence[Sequence[float]], targets: Sequence[float]
) -> Tuple[Optional[RandomForestRegressor], Optional[TrainingReport]]:
    """Fit the forest. Returns (None, None) when there is not enough history."""
    if len(features) < settings.ml_min_samples:
        logger.info(
            "not training: %d rows is below ML_MIN_SAMPLES=%d",
            len(features),
            settings.ml_min_samples,
        )
        return None, None

    X = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float)

    model = RandomForestRegressor(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        random_state=RANDOM_STATE,
        n_jobs=1,
    )

    # Cross-validated error, because training error on a forest is near zero and tells you
    # nothing. Folds are capped by the data: 5 where possible, fewer on a short history.
    folds = max(2, min(5, len(X) // 4))
    try:
        scores = cross_val_score(
            model, X, y, cv=KFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE),
            scoring="neg_mean_absolute_error",
        )
        model_mae = float(-scores.mean())
    except ValueError:
        # Too few rows to split meaningfully; fall back to in-sample error and say so by
        # reporting folds=0 rather than quietly presenting it as cross-validated.
        folds = 0
        model.fit(X, y)
        model_mae = float(np.mean(np.abs(model.predict(X) - y)))

    model.fit(X, y)

    report = TrainingReport(
        trained_at=datetime.now().isoformat(timespec="seconds"),
        sample_count=len(X),
        feature_names=list(FEATURE_NAMES),
        model_mae=round(model_mae, 4),
        baseline_mae=round(_baseline_mae(y), 4),
        folds=folds,
        feature_importances={
            name: round(float(value), 4)
            for name, value in zip(FEATURE_NAMES, model.feature_importances_)
        },
    )
    logger.info(
        "trained on %d rows: MAE %.4f kg/day vs baseline %.4f (%d folds)",
        report.sample_count,
        report.model_mae,
        report.baseline_mae,
        report.folds,
    )
    return model, report


def save(model: RandomForestRegressor, report: TrainingReport) -> pathlib.Path:
    path = artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "report": asdict(report)}, path)
    logger.info("model saved to %s", path)
    return path


def load() -> Tuple[Optional[RandomForestRegressor], Optional[dict]]:
    """Load the persisted model, or (None, None).

    A model whose stored feature order does not match the code is rejected rather than
    used: it would still return numbers, and they would be confident nonsense.
    """
    path = artifact_path()
    if not path.exists():
        return None, None
    try:
        payload = joblib.load(path)
    except Exception:
        # A corrupt or version-mismatched artifact must not take the API down; the
        # arithmetic path still works.
        logger.exception("could not load the model at %s - falling back to arithmetic", path)
        return None, None

    model = payload.get("model")
    report = payload.get("report") or {}
    stored_features = tuple(report.get("feature_names", ()))
    if stored_features and stored_features != FEATURE_NAMES:
        logger.error(
            "model was fitted on %s but the code builds %s - refusing to use it",
            stored_features,
            FEATURE_NAMES,
        )
        return None, None
    return model, report


def predict_daily_consumption(model: RandomForestRegressor, row: Sequence[float]) -> float:
    """Predicted kg for the next day. Never negative - a cylinder cannot gain gas."""
    value = float(model.predict(np.asarray([row], dtype=float))[0])
    return max(0.0, value)


def delete() -> bool:
    """Remove the artifact. Used by tests and by a deliberate retrain-from-scratch."""
    path = artifact_path()
    if path.exists():
        path.unlink()
        return True
    return False
