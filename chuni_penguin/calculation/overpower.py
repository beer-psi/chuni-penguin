import decimal
from decimal import Decimal
from typing import TYPE_CHECKING

from chuni_penguin.utils import floor_to_ndp

from .rating import calculate_whole_rating

if TYPE_CHECKING:
    from chuni_penguin.types import ComboLamp

FC_OVERPOWER_BONUS = Decimal("0.5")
AJ_OVERPOWER_BONUS = Decimal("0.5")
AJC_OVERPOWER_BONUS = Decimal("0.25")


def calculate_overpower_base(score: int, internal_level: float) -> Decimal:
    if score >= 1_007_500:
        sss_bonus = Decimal(score - 1_007_500) / 10000 * 15
        rawop = Decimal(str(internal_level)) * 5 + 10 + sss_bonus
    else:
        rawop = Decimal(calculate_whole_rating(score, internal_level)) / 10000 * 5

    # For rank S and above, OP is floored to the nearest 0.005
    # Otherwise, OP is floored to the nearest 0.05
    rounding = 2 if score >= 975_000 else 1
    op_floor = floor_to_ndp(rawop, rounding)

    with decimal.localcontext() as ctx:
        ctx.rounding = decimal.ROUND_HALF_UP
        op_ceil = round(rawop, rounding)

    return (op_floor + op_ceil) / 2


def calculate_overpower_max(internal_level: float) -> Decimal:
    return Decimal(str(internal_level)) * 5 + 15


def calculate_play_overpower(
    overpower_base: Decimal, combo_lamp: "ComboLamp"
) -> Decimal:
    from chuni_penguin.types import ComboLamp

    play_overpower = overpower_base

    if combo_lamp in (
        ComboLamp.full_combo,
        ComboLamp.all_justice,
        ComboLamp.all_justice_critical,
    ):
        play_overpower += FC_OVERPOWER_BONUS

    if combo_lamp in (ComboLamp.all_justice, ComboLamp.all_justice_critical):
        play_overpower += AJ_OVERPOWER_BONUS

    if combo_lamp == ComboLamp.all_justice_critical:
        play_overpower += AJC_OVERPOWER_BONUS

    return play_overpower
