import argparse
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Generic, NotRequired, TypedDict, TypeVar

from discord.ext import commands

_T = TypeVar("_T")


class AddArgumentKwargs(TypedDict, Generic[_T]):
    action: NotRequired[str | type[argparse.Action]]
    nargs: NotRequired[int | str | None]
    const: NotRequired[Any]
    default: NotRequired[Any]
    type: NotRequired[
        Callable[[str], Any | Awaitable[Any]]
        | argparse.FileType
        | str
        | type[commands.Converter]
        | commands.Converter
    ]
    choices: NotRequired[Iterable[_T] | None]
    required: NotRequired[bool]
    help: NotRequired[str | None]
    metavar: NotRequired[str | tuple[str, ...] | None]
    dest: NotRequired[str | None]
    version: NotRequired[str]
