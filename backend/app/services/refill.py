"""The refill recommendation.

Moved server-side in phase 6 so one place decides it. Phase 5 computed "due soon" in the
refill card from days-remaining against the threshold; with the Dashboard, the Prediction
page and a future notification all able to ask the same question, a client-side rule would
have drifted between them.

**No ordering, no payment, no supplier.** Explicitly out of scope, and the copy the UI shows
says so. This service produces an urgency word and a reason; acting on it is the user's
business.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Urgency words, least to most. The UI renders the word, never just a colour.
NOT_NEEDED = "NOT_NEEDED"
PLAN_AHEAD = "PLAN_AHEAD"
ORDER_NOW = "ORDER_NOW"
URGENT = "URGENT"

# Below this percentage the level alone is urgent, whatever the day count says. A cylinder
# at 4% with a low daily average could otherwise be reported as "a week left", which is
# true on average and useless if tonight's cooking is heavy.
URGENT_PERCENT = Decimal("8")


@dataclass
class Recommendation:
    urgency: str
    should_refill: bool
    days_remaining: Optional[float]
    threshold_days: int
    reason: str


def recommend(
    percentage: Optional[Decimal],
    days_remaining: Optional[Decimal],
    threshold_days: int,
    average_daily_kg: Optional[Decimal] = None,
) -> Recommendation:
    """Decide how urgent a refill is.

    `days_remaining` of None means no prediction exists yet - which is a real state, and
    reported as such rather than defaulted to "fine".
    """
    days = float(days_remaining) if days_remaining is not None else None

    if percentage is not None and Decimal(percentage) <= URGENT_PERCENT:
        return Recommendation(
            urgency=URGENT,
            should_refill=True,
            days_remaining=days,
            threshold_days=threshold_days,
            reason=(
                f"Only {percentage}% of capacity left. Refill now - at this level the "
                "cylinder can run out mid-use even if the daily average suggests longer."
            ),
        )

    if days is None:
        return Recommendation(
            urgency=NOT_NEEDED,
            should_refill=False,
            days_remaining=None,
            threshold_days=threshold_days,
            reason=(
                "No depletion estimate yet. A recommendation appears once at least one "
                "day of consumption has been recorded."
            ),
        )

    if days <= threshold_days:
        return Recommendation(
            urgency=ORDER_NOW,
            should_refill=True,
            days_remaining=days,
            threshold_days=threshold_days,
            reason=(
                f"About {days:.1f} days of gas left, at or below your {threshold_days}-day "
                "reminder. Worth arranging a refill now."
            ),
        )

    # A warning band above the threshold, so the first notice is not also the deadline.
    if days <= threshold_days * 2:
        return Recommendation(
            urgency=PLAN_AHEAD,
            should_refill=False,
            days_remaining=days,
            threshold_days=threshold_days,
            reason=(
                f"About {days:.1f} days left. Nothing urgent, but your {threshold_days}-day "
                "reminder is approaching."
            ),
        )

    detail = f" at about {average_daily_kg} kg/day" if average_daily_kg else ""
    return Recommendation(
        urgency=NOT_NEEDED,
        should_refill=False,
        days_remaining=days,
        threshold_days=threshold_days,
        reason=f"About {days:.1f} days left{detail}. No refill needed yet.",
    )
