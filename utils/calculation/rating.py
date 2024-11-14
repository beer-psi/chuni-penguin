from decimal import Decimal
from typing import Optional

from utils import floor_to_ndp


def calculate_rating(score: int, internal_level: Optional[float]) -> Decimal:
    level_base = Decimal(str(internal_level or 0)) * 10000

    rating100 = Decimal(0)

    if score >= 1_009_000:
        rating100 = level_base + 21_500
    elif score >= 1_007_500:
        rating100 = level_base + 20_000 + (score - 1_007_500)
    elif score >= 1_005_000:
        rating100 = level_base + 15_000 + (score - 1_005_000) * 2
    elif score >= 1_000_000:
        rating100 = level_base + 10_000 + (score - 1_000_000)
    elif score >= 975_000:
        rating100 = level_base + Decimal(score - 975_000) * 2 / 5
    elif score >= 900_000:
        rating100 = level_base - 50_000 + Decimal(score - 900_000) * 2 / 3
    elif score >= 800_000:
        rating100 = (level_base - 50_000) / 2 + (
            (score - 800_000) * ((level_base - 50_000) / 2)
        ) / 100_000
    elif score >= 500_000:
        rating100 = (((level_base - 50_000) / 2) * (score - 500_000)) / 300_000

    if rating100 < 0 and internal_level is not None and internal_level > 0:
        rating100 = Decimal(0)

    return floor_to_ndp(rating100 / 10000, 2)


def calculate_score_for_rating(rating: float, internal_level: float) -> Optional[int]:
    diff = Decimal(str(rating)) * 10000 - Decimal(str(internal_level)) * 10000

    req = None
    if diff >= 21_501:
        req = None
    elif diff >= 20_000:
        req = 1_007_500 + diff - 20_000
    elif diff >= 15_000:
        req = 1_005_000 + (diff - 15_000) / 2
    elif diff >= 10_000:
        req = 1_000_000 + (diff - 10_000)
    else:
        req = 975_000 + diff * 5 / 2

    # Calculation for scores below 975,000 is very complex so it is skipped for now
    # (If your score is below 975,000 you should just git gud)

    return int(req) if req is not None else None
