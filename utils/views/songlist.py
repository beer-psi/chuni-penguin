from collections.abc import Sequence

import discord
import discord.ui
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chunithm_net.models.enums import Difficulty
from database.models import Chart
from utils import yt_search_link

from ._pagination import PaginationView


class SonglistView(PaginationView):
    # tuple is (title, difficulty, sdvx.in id)
    def __init__(self, ctx: Context, charts: Sequence[Chart]):
        super().__init__(ctx, items=charts, per_page=15)

    def format_songlist(
        self, charts: Sequence[Chart], start_index: int = 0
    ) -> discord.Embed:
        songlist = ""
        for idx, chart in enumerate(charts):
            url = (
                chart.sdvxin_chart_view.url
                if chart.sdvxin_chart_view is not None
                else yt_search_link(chart.song.title, chart.difficulty, chart.level)
            )
            songlist += f"{idx + start_index + 1}. {escape_markdown(chart.song.title)} [[{Difficulty.from_short_form(chart.difficulty)} {chart.const}]]({url})\n"
        return discord.Embed(
            description=songlist,
        ).set_footer(text=f"Page {self.page + 1}/{self.max_index + 1}")

    async def callback(self, interaction: discord.Interaction):
        begin = self.page * self.per_page
        end = (self.page + 1) * self.per_page
        await interaction.response.edit_message(
            embed=self.format_songlist(self.items[begin:end], begin), view=self
        )
