"""The seven prediction features (spec §17), and how a training set is built from them.

**What the model predicts, and why it is not "days remaining".**

The obvious target would be days-until-empty, but that is not observable from this data:
a cylinder gets refilled long before it empties, so there is no completed depletion cycle
to learn from - the seeded month has exactly one refill and zero completed cycles. A model
trained on a label nobody measured would be fitting an assumption.

So the model predicts **tomorrow's consumption in kg**, which every day of history does
observe, and days remaining is then derived:

    days_remaining = remaining_kg / predicted_daily_consumption

That is the same final division the arithmetic fallback performs. The difference is what
goes into the denominator: the fallback uses a flat historical mean, while the model can
pick up a trend, a weekday pattern, or the effect of an unusually heavy recent stretch.

**No leakage.** The remaining-gas feature for day *i* is the level at the *end of day i-1*,
not day i. Using day i's own closing level would leak that day's consumption into the
features predicting it, and the model would look far better than it is.
"""

from dataclasses import dataclass
from datetime import date
from statistics import mean, pvariance
from typing import List, Sequence, Tuple

# Order matters: the model is fitted on this order and must be fed it at predict time.
FEATURE_NAMES: Tuple[str, ...] = (
    "current_remaining_kg",
    "average_daily_consumption",
    "avg_7_day",
    "avg_30_day",
    "recent_consumption",
    "consumption_variance",
    "day_of_week",
)

# A training row needs enough prior days for the averages and the variance to mean
# anything. Three is the floor; the 7- and 30-day windows simply use what exists.
MIN_HISTORY_DAYS = 3


@dataclass(frozen=True)
class DayRecord:
    """One day of history: what was used, and the level at the end of the day."""

    day: date
    consumption_kg: float
    remaining_kg: float


def _window_mean(values: Sequence[float], size: int) -> float:
    if not values:
        return 0.0
    window = values[-size:]
    return float(mean(window))


def build_row(history: Sequence[DayRecord], remaining_kg: float, when: date) -> List[float]:
    """Features for a single prediction.

    `history` is every day strictly *before* `when`, oldest first. `remaining_kg` is the
    level the prediction starts from - at predict time that is the current reading; when
    building a training row it is the previous day's closing level.
    """
    used = [record.consumption_kg for record in history]

    return [
        float(remaining_kg),
        float(mean(used)) if used else 0.0,
        _window_mean(used, 7),
        _window_mean(used, 30),
        # The most recent single day, which is what makes a sudden change visible to the
        # model rather than averaged away.
        float(used[-1]) if used else 0.0,
        float(pvariance(used)) if len(used) > 1 else 0.0,
        float(when.weekday()),
    ]


def build_dataset(days: Sequence[DayRecord]) -> Tuple[List[List[float]], List[float]]:
    """Turn a day-by-day history into (X, y) for fitting.

    One row per day that has at least `MIN_HISTORY_DAYS` of history behind it, so a
    31-day history yields 28 rows. That is a small training set, and the metrics reported
    by `model.train` are honest about it.
    """
    ordered = sorted(days, key=lambda record: record.day)

    features: List[List[float]] = []
    targets: List[float] = []
    for index in range(MIN_HISTORY_DAYS, len(ordered)):
        history = ordered[:index]
        today = ordered[index]
        # Level at the start of `today`, i.e. the close of the previous day.
        opening_remaining = history[-1].remaining_kg
        features.append(build_row(history, opening_remaining, today.day))
        targets.append(float(today.consumption_kg))

    return features, targets
