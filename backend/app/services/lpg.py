"""LPG mass arithmetic.

The load cell can only measure the *total* weight sitting on it. The gas left is
that total minus the cylinder's own empty (tare) weight, and the percentage is
measured against the cylinder's rated gas capacity, not against the total.

    remaining = total_weight - empty_weight      floored at 0
    percentage = remaining / capacity * 100      clamped to 0..100

Both guards matter in practice. A load cell reading slightly below the tare
weight is normal drift on a near-empty cylinder and must not produce a negative
quantity of gas, and a freshly filled cylinder can weigh a little over its rated
capacity without the UI being allowed to claim 103%.

Pure functions, no database access, so they are cheap to test directly.
"""

from decimal import Decimal, ROUND_HALF_UP

# Level labels. Always paired with a word in the UI, never colour alone.
NORMAL = "NORMAL"
LOW = "LOW"
CRITICAL = "CRITICAL"

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _q(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def remaining_kg(total_weight_kg: Decimal, empty_weight_kg: Decimal) -> Decimal:
    """Gas remaining, in kg. Never negative."""
    return _q(max(ZERO, Decimal(total_weight_kg) - Decimal(empty_weight_kg)), "0.001")


def percentage(remaining: Decimal, capacity_kg: Decimal) -> Decimal:
    """Percentage of rated capacity, clamped to 0..100.

    A zero or negative capacity would be a corrupt cylinder record rather than a
    real state, so it reports 0 instead of dividing.
    """
    capacity = Decimal(capacity_kg)
    if capacity <= ZERO:
        return ZERO
    raw = Decimal(remaining) / capacity * HUNDRED
    return _q(min(HUNDRED, max(ZERO, raw)), "0.1")


def level_status(
    percent: Decimal, low_threshold: Decimal, critical_threshold: Decimal
) -> str:
    """NORMAL / LOW / CRITICAL from the per-cylinder thresholds in `settings`.

    Thresholds are percentages of capacity, and `critical` is the lower of the
    two (10% is more urgent than 20%). They are compared in that order so a
    misconfigured pair where critical >= low still reports the more severe state
    rather than silently hiding it.
    """
    percent = Decimal(percent)
    if percent <= Decimal(critical_threshold):
        return CRITICAL
    if percent <= Decimal(low_threshold):
        return LOW
    return NORMAL
