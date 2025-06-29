import argparse
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeVar, Unpack, override

from discord.ext import commands
from discord.ext.commands.view import StringView
from discord.utils import MISSING

from ._parser import OPTIONAL_INVISIBLE, DiscordArguments
from ._types import AddArgumentKwargs

CogT = TypeVar("CogT", bound=commands.Cog | None)
BotT = TypeVar("BotT", bound=commands.Bot | commands.AutoShardedBot, covariant=True)
P = ParamSpec("P")
T = TypeVar("T")


def shlex_split(view: StringView) -> list[str]:
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


class FlagCommand(commands.Command[CogT, P, T]):
    def __init__(
        self,
        func: Callable[
            Concatenate[CogT, commands.Context[Any], P], Coroutine[Any, Any, T]
        ]
        | Callable[Concatenate[commands.Context[Any], P], Coroutine[Any, Any, T]],
        /,
        **kwargs: Any,
    ) -> None:
        super().__init__(func, **kwargs)

        if any(
            p.kind not in (p.KEYWORD_ONLY, p.VAR_KEYWORD)
            for _, p in self.params.items()
        ):
            msg = "Flag command callback should only have keyword arguments"
            raise TypeError(msg)

        try:
            arguments: list[tuple[tuple[str, ...], AddArgumentKwargs]] = (
                func.__ext_flags_arguments__  # pyright: ignore[reportFunctionMemberAccess]
            )
        except AttributeError:
            arguments = []

        self.arguments = arguments

    def _get_parser(self, ctx: commands.Context[BotT] | None):
        parser = DiscordArguments(ctx=ctx)

        for name_or_flags, kwargs in self.arguments:
            parser.add_argument(*name_or_flags, **kwargs)  # pyright: ignore[reportArgumentType]

        return parser

    @override
    async def _parse_arguments(self, ctx: commands.Context[BotT]) -> None:
        ctx.args = [ctx] if self.cog is None else [self.cog, ctx]
        ctx.kwargs = {}

        parser = self._get_parser(ctx)

        try:
            namespace, rest = await parser.parse_known_intermixed_args(
                shlex_split(ctx.view)
            )
        except argparse.ArgumentError as e:
            raise commands.BadArgument(str(e)) from None

        ctx.kwargs.update(vars(namespace))

        if not self.ignore_extra and rest:
            msg = f"Too many arguments passed to {self.qualified_name}"
            raise commands.errors.TooManyArguments(msg)

    @property
    @override
    def signature(self) -> str:
        parser = self._get_parser(None)
        parts: list[str] = []

        optionals = []
        positionals = []

        for action in parser._actions:
            if action.help == argparse.SUPPRESS:
                continue

            if action.option_strings:
                optionals.append(action)
            else:
                positionals.append(action)

        for action in optionals:
            part_parts = [action.option_strings[0]]

            if action.nargs != 0:
                part_parts.append(f" {action.metavar or action.dest.upper()}")

                if action.default is not None and action.default != "":
                    part_parts.append(f"={action.default}")

            part = "".join(part_parts)

            if action.required:
                parts.append(f"<{part}>")
            else:
                parts.append(f"[{part}]")

        for action in positionals:
            if action.default is not None and action.default != "":
                if isinstance(action.default, list):
                    displayed_default = f"={' '.join([str(x) for x in action.default])}"
                else:
                    displayed_default = f"={action.default}"
            else:
                displayed_default = ""

            if action.nargs is None:
                parts.append(f"<{action.dest}{displayed_default}>")
            elif action.nargs in (argparse.OPTIONAL, OPTIONAL_INVISIBLE):
                parts.append(f"[{action.dest}{displayed_default}]")
            elif action.nargs == argparse.ZERO_OR_MORE:
                parts.append(f"[{action.dest}{displayed_default} ...]")
            elif action.nargs == argparse.ONE_OR_MORE:
                parts.append(f"<{action.dest}{displayed_default} ...>")
            elif action.nargs in (argparse.REMAINDER, argparse.PARSER):
                parts.append(f"{action.dest} ...")
            elif action.nargs == argparse.SUPPRESS:
                continue

        return " ".join(parts)


class FlagGroup(FlagCommand[CogT, P, T], commands.Group[CogT, P, T]):
    pass


def command(
    name: str = MISSING,
    cls: type[FlagCommand[Any, ..., Any]] = MISSING,
    **attrs: Any,
):
    if cls is MISSING:
        cls = FlagCommand

    def decorator(fn):
        if isinstance(fn, commands.Command):
            msg = "Callback is already a command."
            raise TypeError(msg)

        return cls(fn, name=name, **attrs)

    return decorator


def group(
    name: str = MISSING,
    cls: type[FlagGroup[Any, ..., Any]] = MISSING,
    **attrs: Any,
):
    if cls is MISSING:
        cls = FlagGroup

    return command(name=name, cls=cls, **attrs)


def argument(*name_or_flags: str, **kwargs: Unpack[AddArgumentKwargs]):
    def decorator(fn):
        if isinstance(fn, FlagCommand):
            fn.arguments.insert(0, (name_or_flags, kwargs))
        else:
            if not hasattr(fn, "__ext_flags_arguments__"):
                fn.__ext_flags_arguments__ = []

            fn.__ext_flags_arguments__.insert(0, (name_or_flags, kwargs))

        return fn

    return decorator
