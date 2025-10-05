import pytest

from chuni_penguin.calculation import (
    calculate_rating,
    calculate_score_for_rating,
)


@pytest.mark.parametrize(
    ("score", "chart_constant", "expected"),
    [
        # Test all the cutoffs are where they should be.
        (1_010_000, 12.5, 12.5 + 2.15),
        (1_007_500, 12.5, 12.5 + 2),
        (1_005_000, 12.5, 12.5 + 1.5),
        (1_000_000, 12.5, 12.5 + 1),
        (975_000, 12.5, 12.5),
        (900_000, 12.5, 12.5 - 5),
        (800_000, 12.5, 12.5 - 8.75),
        (500_000, 12.5, 0),
        (0, 12.5, 0),
        # Test some random values in between.
        (987_000, 12.5, 12.5 + 0.48),
        (1_008_000, 12.5, 12.5 + 2.05),
        (1_003_000, 12.5, 12.5 + 1.3),
        (999_000, 12.5, 12.5 + 0.96),
        (980_000, 12.5, 12.5 + 0.2),
        (950_000, 12.5, 12.5 - 1.67),
        (920_000, 12.5, 12.5 - 3.67),
        (810_000, 12.5, 12.5 - 8.38),
        (600_000, 12.5, 12.5 - 11.25),
        (50_000, 12.5, 0),
        # Funny edge cases
        (1_010_000, 0, 2.15),
        (0, 12.5, 0),
        (0, 0, 0),
    ],
)
def test_calculate_rating(score, chart_constant, expected):
    assert (
        pytest.approx(float(calculate_rating(score, chart_constant)), 0.001) == expected
    )


@pytest.mark.parametrize(
    ("rating", "chart_constant", "expected"),
    [
        # Test all the cutoffs are where they should be.
        (14.7, 12.5, None),
        (14.65, 12.5, 1_009_000),
        (14.5, 12.5, 1_007_500),
        (14.0, 12.5, 1_005_000),
        (13.5, 12.5, 1_000_000),
        (12.5, 12.5, 975_000),
        (7.5, 12.5, None),
        # Test some random values in between.
        (12.98, 12.5, 987_000),
        (14.55, 12.5, 1_008_000),
        (13.8, 12.5, 1_003_000),
        (13.46, 12.5, 999_000),
        (12.7, 12.5, 980_000),
    ],
)
def test_calculate_score_for_rating(
    rating: float, chart_constant: float, expected: int | None
):
    assert calculate_score_for_rating(rating, chart_constant) == expected
