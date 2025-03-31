from decimal import Decimal
from typing import Optional

RATING_COEFFICIENTS = {
    1_009_000: 224,
    1_008_999: 222,
    1_007_500: 216,
    1_007_499: 214,
    1_005_000: 211,
    1_000_000: 208,
    999_999: 206,
    990_000: 203,
    975_000: 200,
    974_999: 176,
    950_000: 168,
    925_000: 152,
    900_000: 136,
    899_999: 128,
    800_000: 120,
    700_000: 112,
    600_000: 96,
    500_000: 80,
    400_000: 64,
    300_000: 48,
    200_000: 32,
    100_000: 16,
    0: 0,
}


def calculate_rating(score: int, internal_level: Optional[float]) -> int:
    internal_level_10 = round((internal_level or 0) * 10)
    score = min(1_009_000, score)

    for boundary, coeff in RATING_COEFFICIENTS.items():
        if score >= boundary:
            return int(score * coeff * internal_level_10 / 100_000_000)

    msg = f"Unresolvable score of {score}."
    raise ValueError(msg)


def calculate_score_for_rating(rating: float, internal_level: float) -> Optional[int]:
    rating10000 = int(rating * 10000)
    internal_level_10000 = int(internal_level * 10000)
    coeff = rating10000 - internal_level_10000

    req = None

    if coeff >= 21_500:
        req = None
    elif coeff >= 20_000:
        req = 1_007_500 + coeff - 20_000
    elif coeff >= 15_000:
        req = 1_005_000 + (coeff - 15_000) / 2
    elif coeff >= 10_000:
        req = 1_000_000 + (coeff - 10_000)
    elif coeff >= 0:
        req = 975_000 + coeff * 5 / 2

    # Calculation for scores below 975,000 is very complex so it is skipped for now
    # (If your score is below 975,000 you should just git gud)

    return int(req) if req is not None else None
