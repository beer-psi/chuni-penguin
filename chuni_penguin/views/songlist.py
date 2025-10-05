from typing import Any, override

import discord
import discord.ui
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chunithm_net.models.enums import Difficulty
from database.models import Chart
from utils import yt_search_link

from ._pagination import ListPageSource, PaginationView


class SonglistPageSource(ListPageSource[Chart]):
    def __init__(self, entries: list[Chart], *, per_page: int) -> None:
        super().__init__(entries, per_page=per_page)

    @override
    async def format_page(
        self, menu: "PaginationView", page: list[Chart]
    ) -> dict[str, Any]:
        start = menu.current_page * self.per_page
        songlist = ""

        for idx, chart in enumerate(page):
            url = (
                chart.sdvxin_chart_view.url
                if chart.sdvxin_chart_view is not None
                else yt_search_link(chart.song.title, chart.difficulty, chart.level)
            )
            songlist += f"{idx + start + 1}. {escape_markdown(chart.song.title)} [[{Difficulty.from_short_form(chart.difficulty)} {chart.const}]]({url})\n"

        return {
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                description=songlist,
            ).set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        }


class SonglistView(PaginationView):
    def __init__(self, ctx: Context, charts: list[Chart]):
        super().__init__(ctx, SonglistPageSource(charts, per_page=15))
