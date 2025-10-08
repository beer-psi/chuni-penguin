from decimal import Decimal

from chuni_penguin.networks.types import ComboLamp
from chuni_penguin.utils import floor_to_ndp


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


def calculate_play_overpower(overpower_base: Decimal, combo_lamp: ComboLamp) -> Decimal:
    play_overpower = overpower_base

    if combo_lamp in (
        ComboLamp.full_combo,
        ComboLamp.all_justice,
        ComboLamp.all_justice_critical,
    ):
        play_overpower += Decimal("0.5")

    if combo_lamp in (ComboLamp.all_justice, ComboLamp.all_justice_critical):
        play_overpower += Decimal("0.5")

    if combo_lamp == ComboLamp.all_justice_critical:
        play_overpower += Decimal("0.25")

    return play_overpower
