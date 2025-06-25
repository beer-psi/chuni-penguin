import contextlib
from typing import override

from discord import Interaction, Member, User, app_commands
from discord.ext import commands

from chunithm_net.models.enums import Difficulty, Genres, Rank


class DifficultyConverter(commands.Converter[Difficulty]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Difficulty:
        argument = argument.upper()

        # convert from short form
        # special case MST since I think sdvx.in uses that, might as
        # well support it
        if argument == "MST":
            return Difficulty.MASTER

        # special case this since it's bad
        if argument == "WORLD'S END":
            return Difficulty.WORLDS_END

        # this covers BASIC/ADVANCED/EXPERT/MASTER/ULTIMA full length
        if hasattr(Difficulty, argument):
            return getattr(Difficulty, argument)

        # try to helpfully convert misspellings by using short form
        # e.g. BASI, ULTI, MAST
        with contextlib.suppress(ValueError):
            return Difficulty.from_short_form(argument[:3])

        # give up
        msg = f'Could not infer difficulty name from "{argument}"'
        raise commands.BadArgument(msg)


class GenreConverter(commands.Converter[Genres]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Genres:
        genre_lower = argument.lower()

        if genre_lower.startswith(("pops", "anime")):
            return Genres.POPS_AND_ANIME
        if genre_lower.startswith(("nico", "voca")):
            return Genres.NICONICO
        if genre_lower.startswith(("touhou", "toho", "東方")):
            return Genres.TOUHOU_PROJECT
        if genre_lower.startswith(("original", "chunithm")):
            return Genres.ORIGINAL
        if genre_lower.startswith("variety"):
            return Genres.VARIETY
        if genre_lower.startswith("irodori"):
            return Genres.IRODORIMIDORI
        if genre_lower.startswith(("geki", "ゲキ", "mai", "マイ")):
            return Genres.GEKIMAI

        msg = f'Could not infer genre name from "{argument}".'
        raise commands.BadArgument(msg)


class RankConverter(commands.Converter[Rank]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> Rank:
        try:
            return Rank[argument.upper().replace("+", "p")]
        except ValueError as e:
            msg = f'Could not infer rank from "{argument}".'
            raise commands.BadArgument(msg) from e


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
