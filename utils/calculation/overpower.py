from decimal import Decimal

from chunithm_net.consts import KEY_OVERPOWER_BASE, KEY_OVERPOWER_MAX
from chunithm_net.models.enums import ComboType
from chunithm_net.models.record import Record
from utils import floor_to_ndp


def calculate_overpower_base(score: int, internal_level: float) -> Decimal:
    level_base = Decimal(str(internal_level)) * 10000

    op100 = Decimal(0)

    if score >= 1_007_500:
        op100 = level_base + 20_000 + (score - 1_007_500) * 3
    elif score >= 1_005_000:
        op100 = level_base + 15_000 + (score - 1_005_000) * 2
    elif score >= 1_000_000:
        op100 = level_base + 10_000 + (score - 1_000_000)
    elif score >= 975_000:
        op100 = level_base + Decimal(score - 975_000) * 2 / 5
    elif score >= 900_000:
        op100 = level_base - 50_000 + Decimal(score - 900_000) * 2 / 3
    elif score >= 800_000:
        op100 = (level_base - 50_000) / 2 + (
            (score - 800_000) * ((level_base - 50_000) / 2)
        ) / 100_000
    elif score >= 500_000:
        op100 = (((level_base - 50_000) / 2) * (score - 500_000)) / 300_000

    if op100 < 0:
        op100 = Decimal(0)

    # For rank S and above, OP is floored to the nearest 0.005
    if score >= 975_000:
        return floor_to_ndp(op100 / 1_000, 2) / 2

    # Otherwise, OP is floored to the nearest 0.05
    return floor_to_ndp(op100 / 10_000, 2) * 5


def calculate_overpower_max(internal_level: float) -> Decimal:
    return Decimal(str(internal_level)) * 5 + 15


def calculate_play_overpower(score: Record) -> Decimal:
    play_overpower = score.extras[KEY_OVERPOWER_BASE]

    if score.score == 1010000:
        play_overpower = score.extras[KEY_OVERPOWER_MAX]
    elif score.combo_lamp in {ComboType.ALL_JUSTICE, ComboType.ALL_JUSTICE_CRITICAL}:
        play_overpower += Decimal(1)
    elif score.combo_lamp == ComboType.FULL_COMBO:
        play_overpower += Decimal(0.5)

    return play_overpower
