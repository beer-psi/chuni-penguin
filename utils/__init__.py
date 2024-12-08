import contextlib
import decimal
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import quote

from discord.ext.commands.view import StringView
from discord.utils import escape_markdown
from zoneinfo import ZoneInfo

from chunithm_net.consts import INTERNATIONAL_JACKET_BASE, JACKET_BASE

if TYPE_CHECKING:
    from typing import TypeVar

    from database.models import Alias, SdvxinChartView, Song

    T = TypeVar("T", float | decimal.Decimal, decimal.Decimal, float, str, int)


TOKYO_TZ = ZoneInfo("Asia/Tokyo")


try:
    import orjson  # type: ignore[reportMissingImports]

    def json_dumps(obj):
        return orjson.dumps(obj).decode("utf-8")

    def json_loads(s):
        return orjson.loads(s)

except ModuleNotFoundError:
    import json

    json_dumps = json.dumps
    json_loads = json.loads


class asuppress(contextlib.AbstractAsyncContextManager):
    def __init__(self, *exceptions) -> None:
        self._exceptions = exceptions

    async def __aenter__(self):
        pass

    # Pyright is stupid on this one.
    async def __aexit__(
        self,
        exctype: type[BaseException] | None,
        __exc_value,  # type: ignore[reportGeneralTypeIssues]
        __traceback,  # type: ignore[reportGeneralTypeIssues]
    ) -> Optional[bool]:
        return exctype is not None and issubclass(exctype, self._exceptions)


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


def did_you_mean_text(result: "Song | None", alias: "Alias | None") -> str:
    did_you_mean = ""
    if result is not None:
        did_you_mean = f"Did you mean **{escape_markdown(result.title)}**?"
        if alias is not None:
            did_you_mean = f"Did you mean **{escape_markdown(alias.alias)}** (for **{escape_markdown(result.title)}**)?"

    reply = f"No songs found. {did_you_mean}".strip()
    if did_you_mean:
        reply += "\n(You can also use `addalias <title> <alias>` to add the alias for this server.)"

    return reply


def yt_search_link(title: str, difficulty: str, level: str) -> str:
    if difficulty == "WE":
        difficulty = "WORLD'S END"
    return "https://www.youtube.com/results?search_query=" + quote(
        f'"CHUNITHM" "{title}" "{difficulty}" "{level}"'
    )


def sdvxin_link(view: "SdvxinChartView") -> str:
    id = str(view.id)
    difficulty = view.difficulty

    if "ULT" not in difficulty and "WE" not in difficulty:
        if difficulty == "MAS":
            difficulty = "MST"
        elif difficulty == "BAS":
            difficulty = "BSC"
        return f"https://sdvx.in/chunithm/{id[:2]}/{id}{difficulty.lower()}.htm"

    difficulty = difficulty.replace("WE", "end").lower()
    return f"https://sdvx.in/chunithm/{difficulty[:3]}/{id}{difficulty}{view.end_index or ''}.htm"


def get_jacket_url(song: "Song") -> str:
    current_time = datetime.now(TOKYO_TZ)
    is_maintenance = 4 <= current_time.hour <= 7

    if song.available and not is_maintenance:
        return f"{INTERNATIONAL_JACKET_BASE}/{song.jacket}"

    if not song.removed:
        return f"{JACKET_BASE}/{song.jacket}"

    return song.jacket


def release_to_chunithm_version(date: datetime) -> str:
    if (
        datetime(2015, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 1, 21, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM"
    if (
        datetime(2016, 2, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 7, 28, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM PLUS"
    if (
        datetime(2016, 8, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 1, 26, tzinfo=TOKYO_TZ)
    ):
        return "AIR"
    if (
        datetime(2017, 2, 9, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 8, 3, tzinfo=TOKYO_TZ)
    ):
        return "AIR PLUS"
    if (
        datetime(2017, 8, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 2, 22, tzinfo=TOKYO_TZ)
    ):
        return "STAR"
    if (
        datetime(2018, 3, 8, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 10, 11, tzinfo=TOKYO_TZ)
    ):
        return "STAR PLUS"
    if (
        datetime(2018, 10, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 3, 20, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON"
    if (
        datetime(2019, 4, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 10, 10, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON PLUS"
    if (
        datetime(2019, 10, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2020, 7, 2, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL"
    if (
        datetime(2020, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 1, 7, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL PLUS"
    if (
        datetime(2021, 1, 21, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 4, 28, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE"
    if (
        datetime(2021, 5, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 10, 21, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE LOST"
    if (
        datetime(2021, 11, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 4, 1, tzinfo=TOKYO_TZ)
    ):
        return "NEW"
    if (
        datetime(2022, 4, 14, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 9, 29, tzinfo=TOKYO_TZ)
    ):
        return "NEW PLUS"
    if (
        datetime(2022, 10, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 4, 27, tzinfo=TOKYO_TZ)
    ):
        return "SUN"
    if (
        datetime(2023, 5, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 11, 23, tzinfo=TOKYO_TZ)
    ):
        return "SUN PLUS"
    return "LUMINOUS"
