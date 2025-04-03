from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from rapidfuzz import fuzz, process

from utils.constants import SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.botutils import UtilsCog


class AutocompletersCog(commands.Cog, name="Autocompleters"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

    async def song_title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if len(current) < 3:
            return []

        aliases = [
            x
            for x in self.utils.alias_cache
            if x.guild_id == -1
            or (interaction.guild is None or x.guild_id == interaction.guild.id)
        ]
        results = process.extract(
            current,
            [x.alias for x in aliases],
            scorer=fuzz.QRatio,
            processor=str.lower,
            limit=50,
            score_cutoff=SIMILARITY_THRESHOLD,
        )
        titles = {aliases[r[2]].title for r in results}

        return [app_commands.Choice(name=t, value=t) for t in titles][:25]


async def setup(bot: "ChuniBot"):
    await bot.add_cog(AutocompletersCog(bot))
