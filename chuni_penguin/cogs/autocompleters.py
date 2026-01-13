from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from rapidfuzz import fuzz, process

from chuni_penguin.constants import SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class AutocompletersCog(commands.Cog, name="Autocompleters"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils

    async def song_title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if len(current) < 3:
            return []

        aliases = self.utils.alias_cache[0].copy()

        if (guild_id := interaction.guild_id) is not None and (
            guild_aliases := self.utils.alias_cache.get(guild_id)
        ) is not None:
            aliases.extend(guild_aliases)

        results = process.extract(
            current,
            [x.alias for x in aliases],
            scorer=fuzz.QRatio,
            limit=50,
            score_cutoff=SIMILARITY_THRESHOLD,
        )
        titles = {aliases[r[2]].title for r in results}

        return [app_commands.Choice(name=t, value=t) for t in titles][:25]


async def setup(bot: "ChuniBot"):
    await bot.add_cog(AutocompletersCog(bot))
