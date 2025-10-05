from decimal import Decimal

import pytest

from chuni_penguin.calculation import (
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
)
from chuni_penguin.networks.chunithm_net import ComboType


@pytest.mark.parametrize(
    ("score", "chart_constant", "expected"),
    [
        (979_949, 15.6, 78.99),
        (1_000_063, 15.3, 81.53),
        (1_005_535, 15.1, 83.54),
        (1_007_748, 15.1, 85.87),
    ],
)
def test_calculate_overpower_base(score: int, chart_constant: float, expected: float):
    assert (
        pytest.approx(float(calculate_overpower_base(score, chart_constant)), 0.001)
        == expected
    )


@pytest.mark.parametrize(
    ("chart_constant", "expected"),
    [
        (15.0, 90.0),
        (14.9, 89.5),
        (14.0, 85.0),
        (13.0, 80.0),
        (12.0, 75.0),
    ],
)
def test_calculate_overpower_max(chart_constant: float, expected: float):
    assert (
        pytest.approx(float(calculate_overpower_max(chart_constant)), 0.001) == expected
    )


@pytest.mark.parametrize(
    ("overpower_base", "combo_type", "expected"),
    [
        (Decimal("85.30"), ComboType.NONE, 85.30),
        (Decimal("85.64"), ComboType.FULL_COMBO, 86.14),
        (Decimal("85.96"), ComboType.ALL_JUSTICE, 86.96),
        (Decimal("86.25"), ComboType.ALL_JUSTICE_CRITICAL, 87.50),
    ],
)
def test_calculate_play_overpower(
    overpower_base: Decimal, combo_type: ComboType, expected: float
):
    assert (
        pytest.approx(
            float(calculate_play_overpower(overpower_base, combo_type)), 0.001
        )
        == expected
    )
