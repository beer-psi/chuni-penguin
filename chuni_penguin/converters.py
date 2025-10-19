import contextlib
from dataclasses import dataclass
from typing import NamedTuple, override

from discord import Interaction, Member, User, app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from chuni_penguin.constants import MAX_DIFFICULTY
from chuni_penguin.networks.types import Difficulty, Genre, Rank


class DifficultyConverter(commands.Converter[Difficulty]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Difficulty:
        argument = argument.upper()

        # convert from short form
        # special case MST since I think sdvx.in uses that, might as
        # well support it
        if argument == "MST":
            return Difficulty.master

        # special case this since it's bad
        if argument == "WORLD'S END":
            return Difficulty.worlds_end

        # this covers BASIC/ADVANCED/EXPERT/MASTER/ULTIMA full length
        if hasattr(Difficulty, argument):
            return getattr(Difficulty, argument)

        # try to helpfully convert misspellings by using short form
        # e.g. BASI, ULTI, MAST
        with contextlib.suppress(ValueError):
            return Difficulty(argument[:3])

        # give up
        msg = f'Could not infer difficulty name from "{argument}"'
        raise commands.BadArgument(msg)


class GenreConverter(commands.Converter[Genre]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Genre:
        genre_lower = argument.lower()

        if genre_lower.startswith(("pops", "anime")):
            return Genre.pops_and_anime
        if genre_lower.startswith(("nico", "voca")):
            return Genre.niconico
        if genre_lower.startswith(("touhou", "toho", "東方")):
            return Genre.touhou_project
        if genre_lower.startswith(("original", "chunithm")):
            return Genre.original
        if genre_lower.startswith("variety"):
            return Genre.variety
        if genre_lower.startswith("irodori"):
            return Genre.irodorimidori
        if genre_lower.startswith(("geki", "ゲキ", "mai", "マイ")):
            return Genre.gekimai

        msg = f'Could not infer genre name from "{argument}".'
        raise commands.BadArgument(msg)


class RankConverter(commands.Converter[Rank]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Rank:
        try:
            return Rank[argument.lower().replace("+", "p")]
        except ValueError as e:
            msg = f'Could not infer rank from "{argument}".'
            raise commands.BadArgument(msg) from e


@dataclass
class Level:
    level: str
    const: float | None

    @property
    def inferred_const(self):
        return self.const or float(self.level.replace("+", ".5", 1))

    @property
    def inferred_max_const(self):
        if self.const is not None:
            return self.const

        if self.level.endswith("+"):
            return float(self.level.replace("+", ".9", 1))

        return (int(self.level) * 10 + 4) / 10

    def __str__(self):
        return str(self.const) if self.const is not None else self.level


class LevelRange(NamedTuple):
    min_level: Level | None
    max_level: Level | None

    def __str__(self) -> str:
        if self.min_level is not None and self.max_level is not None:
            return f"{self.min_level}-{self.max_level}"
        if self.min_level is not None:
            return f"{self.min_level}-"
        if self.max_level is not None:
            return f"-{self.max_level}"

        return "-"


class LevelConverter(commands.Converter[Level]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Level:
        # covers regular levels (14)
        with contextlib.suppress(ValueError):
            whole = int(argument)

            if whole < 1 or whole > MAX_DIFFICULTY:
                msg = f'Invalid level "{escape_markdown(argument)}". Must be between 1 and {MAX_DIFFICULTY}.'
                raise commands.BadArgument(msg)

            return Level(argument, None)

        # covers plus levels
        if argument.endswith("+"):
            with contextlib.suppress(ValueError):
                whole = int(argument[:-1])

                if whole < 7:
                    msg = f'Invalid level "{escape_markdown(argument)}". Only level 7 and above have plus levels.'
                    raise commands.BadArgument(msg)

                const = (whole * 10 + 5) / 10

                if const > MAX_DIFFICULTY:
                    msg = f'Invalid level "{escape_markdown(argument)}". Must be between 1 and {MAX_DIFFICULTY}.'
                    raise commands.BadArgument(msg)

                return Level(argument, None)

        # covers chart constants (14.9)
        with contextlib.suppress(ValueError):
            const = float(argument)

            if const < 1 or const > MAX_DIFFICULTY:
                msg = f'Invalid level "{escape_markdown(argument)}". Must be between 1 and {MAX_DIFFICULTY}.'
                raise commands.BadArgument(msg)

            whole = int(const)
            decimal = round(const * 10) - whole * 10

            return Level(f"{whole}{'+' if decimal >= 5 else ''}", const)

        msg = f'Could not infer level or chart constant from "{escape_markdown(argument)}".'
        raise commands.BadArgument(msg)


class LevelRangeConverter(commands.Converter[Level | LevelRange]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Level | LevelRange:
        min_level_str, separator, max_level_str = argument.partition("-")
        level_converter = LevelConverter()

        if len(max_level_str) <= 0 and len(separator) <= 0:
            return await level_converter.convert(ctx, min_level_str)

        min_level = (
            await level_converter.convert(ctx, min_level_str)
            if len(min_level_str) > 0
            else None
        )
        max_level = (
            await level_converter.convert(ctx, max_level_str)
            if len(max_level_str) > 0
            else None
        )

        if (
            min_level is not None
            and max_level is not None
            and min_level.inferred_const > max_level.inferred_const
        ):
            msg = f"Invalid range: minimum level {min_level} is larger than maximum level {max_level}"
            raise commands.BadArgument(msg)

        return LevelRange(min_level, max_level)


# TODO: Consider inheriting from commands.clean_content instead so we
# get mention scrubbing and markdown scrubbing, but I think
# we have a bunch of aliases in the production database that's just
# emotes and mentions of people, so it's probably not possible.
# At least we can force casing to always be lowercase.
class AliasNameConverter(commands.Converter[str]):
    def __init__(self, *, lower: bool = False) -> None:
        super().__init__()
        self.lower = lower

    @override
    async def convert(self, ctx: commands.Context, argument: str) -> str:
        return argument.strip().lower() if self.lower else argument.strip()


class AliasNameTransformer(app_commands.Transformer):
    def __init__(self, *, lower: bool = False) -> None:
        super().__init__()
        self.lower = lower

    @override
    async def transform(self, interaction: Interaction, value: str) -> str:
        return value.strip().lower() if self.lower else value.strip()


class MemberOrUserConverter(commands.Converter[Member | User]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Member | User:
        for converter in (commands.MemberConverter, commands.UserConverter):
            with contextlib.suppress(commands.BadArgument):
                return await converter().convert(ctx, argument)

        raise commands.UserNotFound(argument)
