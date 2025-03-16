import contextlib
from typing import override

from discord import Interaction, app_commands
from discord.ext import commands

from chunithm_net.models.enums import Difficulty


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
        msg = f'Could not infer difficuty name from "{argument}"'
        raise commands.BadArgument(msg)


# TODO: Consider inheriting from commands.clean_content instead so we
# get mention scrubbing and markdown scrubbing, but I think
# we have a bunch of aliases in the production database that's just
# emotes and mentions of people, so it's probably not possible.
# At least we can force casing to always be lowercase.
class AliasNameConverter(commands.Converter[str]):
    @override
    async def convert(self, ctx: commands.Context, argument: str) -> str:
        return argument.lower()


class AliasNameTransformer(app_commands.Transformer):
    @override
    async def transform(self, interaction: Interaction, value: str) -> str:
        return value.lower()
