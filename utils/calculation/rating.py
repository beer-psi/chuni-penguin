from decimal import Decimal
from typing import Optional


def calculate_rating(score: int, internal_level: Optional[float]) -> Decimal:
    internal_level_10000 = int((internal_level or 0) * 10000)

    if score >= 1_009_000:
        rating10000 = internal_level_10000 + 21_500
    elif score >= 1_007_500:
        rating10000 = internal_level_10000 + 20_000 + (score - 1_007_500)
    elif score >= 1_005_000:
        rating10000 = internal_level_10000 + 15_000 + (score - 1_005_000) * 2
    elif score >= 1_000_000:
        rating10000 = internal_level_10000 + 10_000 + (score - 1_000_000)
    elif score >= 975_000:
        rating10000 = int(internal_level_10000 + (score - 975_000) * 2 / 5)
    elif score >= 900_000:
        rating10000 = int(internal_level_10000 - 50_000 + (score - 900_000) * 2 / 3)
    elif score >= 800_000:
        rating10000 = int(
            (internal_level_10000 - 50_000) / 2
            + ((score - 800_000) * ((internal_level_10000 - 50_000) / 2)) / 100_000
        )
    elif score >= 500_000:
        rating10000 = int(
            (((internal_level_10000 - 50_000) / 2) * (score - 500_000)) / 300_000
        )
    else:
        rating10000 = 0

    if rating10000 < 0 and internal_level is not None and internal_level > 0:
        rating10000 = 0

    return Decimal(rating10000) / 10000


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
