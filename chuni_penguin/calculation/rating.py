from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chuni_penguin.types import ComboLamp


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


def calculate_whole_ongeki_rating(
    score: int, internal_level: float | None, combo_lamp: "ComboLamp"
) -> int:
    from chuni_penguin.types import ComboLamp

    il10000 = int((internal_level or 0) * 10000)
    lamp_bonus = 0

    # assume FB
    if combo_lamp == ComboLamp.all_justice_critical:
        lamp_bonus = 4000
    elif combo_lamp == ComboLamp.all_justice:
        lamp_bonus = 3500
    elif combo_lamp == ComboLamp.full_combo:
        lamp_bonus = 1500

    if score == 1_010_000:
        return il10000 + 3000 + lamp_bonus + 20_000
    if score >= 1_009_000:
        return il10000 + 3000 + lamp_bonus + 17_500 + (score - 1_009_000) * 2500 // 1000
    if score >= 1_007_500:
        return il10000 + 2000 + lamp_bonus + 12_500 + (score - 1_007_500) * 5000 // 1500
    if score >= 1_000_000:
        return il10000 + 1000 + lamp_bonus + 7_500 + (score - 1_000_000) * 5000 // 7500
    if score >= 975_000:
        return il10000 + lamp_bonus + (score - 975_000) * 7500 // 25_000
    if score >= 925_000:
        return il10000 + lamp_bonus - 40_000 + (score - 925_000) * 40_000 // 50_000
    if score >= 800_000:
        return il10000 + lamp_bonus - 60_000 + (score - 800_000) * 20_000 // 125_000

    return 0


def calculate_ongeki_rating(
    score: int, internal_level: float | None, combo_lamp: "ComboLamp"
) -> Decimal:
    return (
        Decimal(calculate_whole_ongeki_rating(score, internal_level, combo_lamp) // 10)
        / 1000
    )


def calculate_ongeki_platinum_rating(score: int, internal_level: float):
    il10 = int((internal_level or 0) * 10)
    rank = 0

    if score >= 1009980:
        rank = 5
    elif score >= 1009960:
        rank = 4
    elif score >= 1009940:
        rank = 3
    elif score >= 1009920:
        rank = 2
    elif score >= 1009900:
        rank = 1

    return Decimal(rank * il10 * il10 // 100) / 1000


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
        from chuni_penguin.utils import round_to_nearest

        return round_to_nearest(int(req), 50)

    return None
