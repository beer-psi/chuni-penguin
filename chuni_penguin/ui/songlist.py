from collections.abc import Sequence
from typing import override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chuni_penguin.database import Chart
from chuni_penguin.types import Difficulty
from chuni_penguin.utils import sdvxin_link, yt_search_link

from ._pagination import FormatPageReturn, ListPageSource, PaginationView


class SonglistPageSource(ListPageSource[Chart]):
    def __init__(self, entries: list[Chart], *, per_page: int) -> None:
        super().__init__(entries, per_page=per_page)

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[Chart]
    ) -> FormatPageReturn:
        start = menu.current_page * self.per_page
        songlist = ""

        for idx, chart in enumerate(page):
            url = (
                sdvxin_link(chart.sdvxin_chart_view)
                if chart.sdvxin_chart_view is not None
                else yt_search_link(chart.song.title, chart.difficulty)
            )
            songlist += f"{idx + start + 1}. {escape_markdown(chart.song.title)} [[{Difficulty(chart.difficulty)} {chart.const or chart.level}]]({url})\n"

        return {
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                description=songlist,
            )
        }


class SonglistView(PaginationView):
    def __init__(self, ctx: Context, charts: list[Chart]):
        super().__init__(ctx, SonglistPageSource(charts, per_page=15))
