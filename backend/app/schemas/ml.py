"""Model status and training responses."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class TrainingReportModel(BaseModel):
    trained_at: str
    sample_count: int
    feature_names: List[str]
    # Mean absolute error in kg/day. Cross-validated when `folds` > 0; in-sample when 0,
    # which the field makes visible rather than hiding.
    model_mae: float
    # Error from predicting the historical mean every day - what the model has to beat.
    baseline_mae: float
    folds: int
    feature_importances: Dict[str, float]


class ModelStatusResponse(BaseModel):
    trained: bool
    # Trained but idle is a real state: a model that cross-validates worse than a flat
    # average is kept for inspection and not used, and predictions stay on the arithmetic
    # path labelled ESTIMATE.
    in_use: bool
    beats_baseline: bool
    artifact_path: str
    min_samples_required: int
    report: Optional[TrainingReportModel] = None


class TrainingResponse(BaseModel):
    trained: bool
    # False means the fit was worse than a flat average. Reported rather than suppressed:
    # a model that loses to the mean is information, not a failure to hide.
    beats_baseline: bool
    report: TrainingReportModel
