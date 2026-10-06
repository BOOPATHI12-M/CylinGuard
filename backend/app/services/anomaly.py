"""The four-state anomaly ladder.

The one rule that matters here, from spec §22:

    **Abnormal consumption alone is never a leak.**

High consumption has innocent explanations - a party, a long cooking session, a
guest staying - and a system that cries "LEAK" at them gets ignored, which is worse
than saying nothing. So consumption on its own tops out at UNUSUAL_CONSUMPTION.
Escalation past that requires the MQ-6 to independently agree that there is gas in
the air:

    gas normal   + consumption normal    -> NORMAL
    gas normal   + consumption abnormal  -> UNUSUAL_CONSUMPTION   (never a leak)
    gas exceeded + consumption normal    -> POSSIBLE_LEAK
    gas exceeded + consumption abnormal  -> CRITICAL_LEAK         (two signals agree)

Pure functions. No database, no side effects, no alerts raised - the caller decides
what to do with the verdict.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

NORMAL = "NORMAL"
UNUSUAL_CONSUMPTION = "UNUSUAL_CONSUMPTION"
POSSIBLE_LEAK = "POSSIBLE_LEAK"
CRITICAL_LEAK = "CRITICAL_LEAK"

# Worst-first, so callers can compare severity without a lookup table.
SEVERITY_ORDER = [NORMAL, UNUSUAL_CONSUMPTION, POSSIBLE_LEAK, CRITICAL_LEAK]

ZERO = Decimal("0")


@dataclass
class AnomalyVerdict:
    state: str
    deviation_percent: Decimal
    consumption_abnormal: bool
    gas_exceeded: bool
    # Plain-language reasons, so an alert message can explain itself rather than
    # showing a bare state word.
    reasons: List[str] = field(default_factory=list)

    @property
    def is_leak(self) -> bool:
        return self.state in (POSSIBLE_LEAK, CRITICAL_LEAK)

    def worse_than(self, other: str) -> bool:
        return SEVERITY_ORDER.index(self.state) > SEVERITY_ORDER.index(other)


def deviation_percent(today_kg: Decimal, average_kg: Decimal) -> Decimal:
    """How far above the historical average today is, as a percentage.

    Returns 0 when there is no average to compare against: with no history, nothing
    can be called abnormal, and dividing by zero to find out would be worse.
    """
    average = Decimal(average_kg)
    if average <= ZERO:
        return ZERO
    raw = (Decimal(today_kg) - average) / average * Decimal("100")
    return raw.quantize(Decimal("0.1"))


def evaluate(
    today_kg: Decimal,
    average_kg: Decimal,
    anomaly_threshold_percent: Decimal,
    gas_value: int,
    gas_threshold: int,
    *,
    has_history: bool = True,
) -> AnomalyVerdict:
    """Classify the current state from consumption and gas together."""
    deviation = deviation_percent(today_kg, average_kg)

    # Without history there is no baseline, so consumption cannot be judged. The gas
    # sensor still can be - a leak on day one is still a leak.
    consumption_abnormal = bool(
        has_history
        and Decimal(average_kg) > ZERO
        and deviation >= Decimal(anomaly_threshold_percent)
    )
    gas_exceeded = int(gas_value) >= int(gas_threshold)

    reasons: List[str] = []
    if consumption_abnormal:
        reasons.append(
            f"consumption {deviation}% above the {average_kg} kg/day average"
        )
    if gas_exceeded:
        reasons.append(f"MQ-6 reading {gas_value} at or above the threshold {gas_threshold}")

    if gas_exceeded and consumption_abnormal:
        state = CRITICAL_LEAK
    elif gas_exceeded:
        state = POSSIBLE_LEAK
    elif consumption_abnormal:
        # Deliberately stops here. Without gas corroboration this is not a leak.
        state = UNUSUAL_CONSUMPTION
    else:
        state = NORMAL

    return AnomalyVerdict(
        state=state,
        deviation_percent=deviation,
        consumption_abnormal=consumption_abnormal,
        gas_exceeded=gas_exceeded,
        reasons=reasons,
    )
