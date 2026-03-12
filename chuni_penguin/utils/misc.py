import asyncio
import contextlib
import decimal
import io
import tempfile
from collections.abc import AsyncIterator
from functools import total_ordering
from typing import IO, TYPE_CHECKING, Any, Literal, TypeVar, overload
from zoneinfo import ZoneInfo

from discord.ext.commands.view import StringView
from discord.utils import MISSING

if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryMode,
        OpenBinaryModeReading,
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextMode,
    )

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
        return round(number, dp)


def round_to_nearest(number: "T", value: int) -> "T":
    digit_count = len(str(value))

    multiplier: int = 10**digit_count // value
    round_dp = -digit_count

    return type(number)(
        round(decimal.Decimal(number * multiplier), round_dp) / multiplier
    )


@total_ordering
class Reversor:
    __slots__ = ("obj",)

    def __init__(self, obj: object):
        self.obj = obj

    def __eq__(self, value: object, /) -> bool:
        if isinstance(value, Reversor):
            return value.obj == self.obj

        return value == self.obj

    def __lt__(self, value: object, /) -> bool:
        if isinstance(value, Reversor):
            return value.obj < self.obj  # pyright: ignore[reportOperatorIssue]

        return value < self.obj  # pyright: ignore[reportOperatorIssue]


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    mode: "OpenTextMode",
    buffering: int = -1,
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[io.TextIOWrapper]: ...


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    mode: "OpenBinaryMode",
    buffering: Literal[0],
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[io.FileIO]: ...


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    *,
    buffering: Literal[0],
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    errors: str | None = None,
) -> AsyncIterator[io.FileIO]: ...


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    mode: "OpenBinaryModeWriting",
    buffering: Literal[-1, 1] = -1,
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[io.BufferedWriter]: ...


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    mode: "OpenBinaryModeReading",
    buffering: Literal[-1, 1] = -1,
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[io.BufferedReader]: ...


@overload
@contextlib.asynccontextmanager
def AsyncTemporaryFile(
    mode: "OpenBinaryModeUpdating" = "w+b",
    buffering: Literal[-1, 1] = -1,
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[io.BufferedRandom]: ...


@contextlib.asynccontextmanager
async def AsyncTemporaryFile(
    mode: "OpenTextMode | OpenBinaryMode" = "w+b",
    buffering: int = -1,
    encoding: str | None = None,
    newline: str | None = None,
    suffix: str | None = None,
    prefix: str | None = None,
    dir: str | None = None,
    *,
    errors: str | None = None,
) -> AsyncIterator[IO[Any]]:
    """
    A :class:`tempfile.TemporaryFile` that is opened and closed asynchronously.
    """

    fp = await asyncio.to_thread(
        tempfile.TemporaryFile,
        mode,
        buffering,
        encoding,
        newline,
        suffix,
        prefix,
        dir,
        errors=errors,
    )

    try:
        yield fp
    finally:
        if fp is not MISSING:
            await asyncio.to_thread(fp.close)
