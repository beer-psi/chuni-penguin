from decimal import Decimal

from chuni_penguin.utils import round_to_nearest


def calculate_whole_rating(score: int, internal_level: float | None) -> int:
    il10000 = int((internal_level or 0) * 10000)

    if score >= 1_009_000:
        return il10000 + 21_500
    if score >= 1_007_500:
        return il10000 + 20_000 + (score - 1_007_500)
    if score >= 1_005_000:
        return il10000 + 15_000 + (score - 1_005_000) * 2
    if score >= 1_000_000:
        return il10000 + 10_000 + (score - 1_000_000)
    if score >= 975_000:
        return int(il10000 + (score - 975_000) * 2 / 5)
    if score >= 900_000:
        effective_il10000 = max(il10000 - 50_000, 0)
        return int(
            effective_il10000
            + (score - 900_000) / 75_000 * (il10000 - effective_il10000)
        )
    if score >= 800_000:
        effective_il10000 = max(il10000 - 50_000, 0)
        return int(
            effective_il10000 / 2
            + ((score - 800_000) / 100_000 * (effective_il10000 / 2))
        )
    if score >= 500_000:
        effective_il10000 = max(il10000 - 50_000, 0)
        return int((score - 500_000) / 300_000 * (effective_il10000 / 2))

    return 0


def calculate_rating(score: int, internal_level: float | None) -> Decimal:
    return Decimal(calculate_whole_rating(score, internal_level) // 100) / 100


def calculate_score_for_rating(rating: float, internal_level: float) -> int | None:
    rating10000 = int(round(rating, 2) * 10000)

    # Fast path: if rating is 0 then required score is 0
    if rating10000 == 0:
        return 0

    il10000 = int(round(internal_level, 2) * 10000)
    sub_s_il10000 = max(il10000 - 50_000, 0)
    coeff = rating10000 - il10000

    req = None

    if coeff > 21_500:
        req = None
    elif coeff >= 20_000:
        req = 1_007_500 + coeff - 20_000
    elif coeff >= 15_000:
        req = 1_005_000 + (coeff - 15_000) / 2
    elif coeff >= 10_000:
        req = 1_000_000 + (coeff - 10_000)
    elif coeff >= 0:
        req = 975_000 + coeff * 5 / 2
    elif rating10000 >= sub_s_il10000:
        req = (rating10000 - sub_s_il10000) / (
            il10000 - sub_s_il10000
        ) * 75_000 + 900_000
    elif rating10000 >= sub_s_il10000 / 2:
        # req = (rating10000 - sub_s_il10000 / 2) / (sub_s_il10000 / 2) * 100_000 + 800_000
        #     = (rating10000 / (sub_s_il10000 / 2) - 1) * 100_000 + 800_000
        req = (rating10000 * 2 / sub_s_il10000 - 1) * 100_000 + 800_000
    elif rating10000 >= 0:
        # req = (rating10000 / (sub_s_il10000 / 2)) * 300_000 + 500_000
        req = (rating10000 * 2 / sub_s_il10000) * 300_000 + 500_000

    # Fix rounding issues
    if req is not None:
        return round_to_nearest(int(req), 50)

    return None
