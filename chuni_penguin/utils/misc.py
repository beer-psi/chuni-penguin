import decimal
from typing import TypeVar
from zoneinfo import ZoneInfo

from discord.ext.commands.view import StringView

T = TypeVar("T", float | decimal.Decimal, decimal.Decimal, float, str, int)
TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def shlex_split(s: str) -> list[str]:
    view = StringView(s)
    result = []

    while not view.eof:
        view.skip_ws()

        if view.eof:
            break

        word = view.get_quoted_word()

        if word is None:
            break

        result.append(word)

    return result


# rounding a decimal should be safe.
def floor_to_ndp(number: decimal.Decimal, dp: int) -> decimal.Decimal:
    if not isinstance(number, decimal.Decimal):
        msg = "Flooring an arbitrary floating point number will cause inaccuracies. Use the Decimal class."
        raise TypeError(msg)

    with decimal.localcontext() as ctx:
        ctx.rounding = decimal.ROUND_FLOOR
        return round(decimal.Decimal(number), dp)


def round_to_nearest(number: "T", value: int) -> "T":
    digit_count = len(str(value))

    multiplier: int = 10**digit_count // value
    round_dp = -digit_count

    return type(number)(
        round(decimal.Decimal(number * multiplier), round_dp) / multiplier
    )
