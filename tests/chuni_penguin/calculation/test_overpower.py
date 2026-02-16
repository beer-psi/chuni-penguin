from decimal import Decimal

import pytest

from chuni_penguin.calculation import (
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
)
from chuni_penguin.networks.types import ComboLamp


@pytest.mark.parametrize(
    ("score", "chart_constant", "expected"),
    [
        (979_949, 15.6, Decimal("78.985")),
        (1_000_063, 15.3, Decimal("81.53")),
        (1_005_535, 15.1, Decimal("83.535")),
        (1_007_748, 15.1, Decimal("85.87")),
    ],
)
def test_calculate_overpower_base(score: int, chart_constant: float, expected: Decimal):
    assert expected == calculate_overpower_base(score, chart_constant)


@pytest.mark.parametrize(
    ("chart_constant", "expected"),
    [
        (15.0, Decimal("90.0")),
        (14.9, Decimal("89.5")),
        (14.0, Decimal("85.0")),
        (13.0, Decimal("80.0")),
        (12.0, Decimal("75.0")),
    ],
)
def test_calculate_overpower_max(chart_constant: float, expected: Decimal):
    assert expected == calculate_overpower_max(chart_constant)


@pytest.mark.parametrize(
    ("overpower_base", "combo_type", "expected"),
    [
        (Decimal("85.30"), ComboLamp.none, Decimal("85.30")),
        (Decimal("85.64"), ComboLamp.full_combo, Decimal("86.14")),
        (Decimal("85.96"), ComboLamp.all_justice, Decimal("86.96")),
        (Decimal("86.25"), ComboLamp.all_justice_critical, Decimal("87.50")),
    ],
)
def test_calculate_play_overpower(
    overpower_base: Decimal, combo_type: ComboLamp, expected: Decimal
):
    assert expected == calculate_play_overpower(overpower_base, combo_type)
