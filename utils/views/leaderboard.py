from collections.abc import Sequence
from typing import override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chunithm_net.models.enums import Difficulty, Rank
from chunithm_net.models.leaderboard import Leaderboard, LeaderboardEntry
from database.models import Chart, Song
from utils import get_jacket_url
from utils.components.chart_card_embed import ChartCardEmbed
from utils.ranks import rank_icon

from ._pagination import PaginationView


class LeaderboardView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        leaderboard: Leaderboard,
        song: Song,
        difficulty: Difficulty,
        chart: Chart | None = None,
        per_page: int = 10,
    ):
        super().__init__(ctx, leaderboard.ranking, per_page)

        self.leaderboard: Leaderboard = leaderboard
        self.song: Song = song
        self.difficulty: Difficulty = difficulty
        self.chart: Chart | None = chart

    def format_page(self, items: Sequence[LeaderboardEntry], start_index: int = 0):
        if self.chart is not None:
            info_embed = ChartCardEmbed(self.chart)
        else:
            info_embed = discord.Embed(
                description=f"**{escape_markdown(self.song.title)} [{self.difficulty}]**",
            )
            info_embed.set_thumbnail(url=get_jacket_url(self.song))

        description = ""

        for item in items:
            description += f"`{item.position}` {item.player_name.ljust(8, "　")} ▸ {rank_icon(Rank.from_score(item.score))} ▸ {item.score}"

            if item.ajc_count is not None:
                description += f" ▸ AJC count: {item.ajc_count}"

            description += f" ▸ <t:{int(item.last_raised.timestamp())}:f>\n"

        leaderboard_embed = discord.Embed(
            color=self.difficulty.color(),
            description=description,
            timestamp=self.leaderboard.updated_at,
        )

        return [info_embed, leaderboard_embed]

    @override
    async def callback(self, interaction: discord.Interaction):
        begin = self.page * self.per_page
        end = (self.page + 1) * self.per_page

        await interaction.response.edit_message(
            embeds=self.format_page(self.items[begin:end], begin),
            view=self,
        )
