"""The tare-weight arithmetic. Pure functions, no database."""

from decimal import Decimal

import pytest

from app.services.lpg import CRITICAL, LOW, NORMAL, level_status, percentage, remaining_kg

EMPTY = Decimal("15.000")
CAPACITY = Decimal("14.200")


def test_remaining_is_total_minus_tare():
    assert remaining_kg(Decimal("23.308"), EMPTY) == Decimal("8.308")


def test_remaining_never_negative():
    """A load cell reading under the tare weight is drift, not negative gas."""
    assert remaining_kg(Decimal("14.900"), EMPTY) == Decimal("0.000")


def test_percentage_matches_the_seeded_figure():
    assert percentage(Decimal("8.308"), CAPACITY) == Decimal("58.5")


def test_percentage_clamped_at_100():
    """An overfilled cylinder must not report 103%."""
    assert percentage(Decimal("14.600"), CAPACITY) == Decimal("100.0")


def test_percentage_clamped_at_zero():
    assert percentage(Decimal("-1.000"), CAPACITY) == Decimal("0.0")


def test_percentage_survives_zero_capacity():
    """A corrupt cylinder row must not raise ZeroDivisionError."""
    assert percentage(Decimal("5.000"), Decimal("0.000")) == Decimal("0")


@pytest.mark.parametrize(
    "percent,expected",
    [
        (Decimal("58.5"), NORMAL),
        (Decimal("20.1"), NORMAL),
        (Decimal("20.0"), LOW),      # boundary is inclusive
        (Decimal("10.1"), LOW),
        (Decimal("10.0"), CRITICAL),  # boundary is inclusive
        (Decimal("0.0"), CRITICAL),
    ],
)
def test_level_status_boundaries(percent, expected):
    assert level_status(percent, Decimal("20.00"), Decimal("10.00")) == expected


def test_misconfigured_thresholds_report_the_more_severe_state():
    """If critical >= low, severity must not be silently hidden."""
    assert level_status(Decimal("15.0"), Decimal("10.00"), Decimal("20.00")) == CRITICAL
