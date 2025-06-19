from typing import Any, override
from urllib.parse import quote

import discord
import discord.utils
from discord.ext.commands import Context
from discord.utils import escape_markdown
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chunithm_net.models.enums import Difficulty
from database.models import Chart, Song
from utils import get_jacket_url, yt_search_link

from ._pagination import ListPageSource, PaginationView


class SongInfoPageSource(ListPageSource[Song]):
    def __init__(self, entries: list[Song], *, detailed: bool) -> None:
        super().__init__(entries, per_page=1)
        self.detailed: bool = detailed

    @override
    async def format_page(
        self, menu: "PaginationView", page: list[Song]
    ) -> dict[str, Any]:
        embeds: list[discord.Embed] = []

        async with menu.ctx.bot.begin_db_session() as session:
            for song in page:
                stmt = (
                    select(Chart)
                    .where(Chart.song_id == song.id)
                    .order_by(Chart.id)
                    .options(joinedload(Chart.sdvxin_chart_view))
                )
                charts = (await session.execute(stmt)).scalars().all()

                song_description = "-# "
                song_description += " / ".join(
                    [escape_markdown(x.alias) for x in song.aliases if x.guild_id == -1]
                )

                song_description += "\n"

                if not song.available:
                    if song.removed:
                        song_description += "**This song is removed.**\n\n"
                    else:
                        song_description += "**This song is not available in CHUNITHM International.**\n\n"
                else:
                    song_description += "\n"

                displayed_version = song.version
                displayed_bpm = "Unknown"

                if song.release is not None:
                    displayed_version += f" ({song.release})"

                if song.bpm is not None:
                    displayed_bpm = str(song.bpm)

                    if (
                        song.min_bpm is not None
                        and song.max_bpm is not None
                        and song.min_bpm != song.max_bpm
                    ):
                        displayed_bpm = (
                            f"{displayed_bpm} ({song.min_bpm}~{song.max_bpm})"
                        )

                song_description += (
                    f"**Artist**: {escape_markdown(song.artist)}\n"
                    f"**Category**: {song.genre}\n"
                    f"**Version**: {displayed_version}\n"
                )

                for chart in charts:
                    if chart.version is not None:
                        difficulty = Difficulty.from_short_form(chart.difficulty)

                        song_description += (
                            f"**Version ({difficulty})**: {chart.version}\n"
                        )

                song_description += f"**BPM**: {displayed_bpm}\n"

                embed = discord.Embed(
                    title=song.title,
                    color=discord.Color.yellow(),
                ).set_thumbnail(url=get_jacket_url(song))

                chart_level_desc = []

                for chart in charts:
                    url = (
                        chart.sdvxin_chart_view.url
                        if chart.sdvxin_chart_view is not None
                        else yt_search_link(song.title, chart.difficulty, chart.level)
                    )

                    if self.detailed:
                        difficulty = Difficulty.from_short_form(chart.difficulty)

                        link_text = f"Lv.{chart.level}"
                        if chart.const is not None:
                            link_text += f" ({chart.const:.1f})"

                        desc = f"{difficulty.emoji()} [{link_text}]({url})"
                    else:
                        if chart.difficulty == "WE":
                            displayed_difficulty = "WORLD'S END"
                        else:
                            displayed_difficulty = chart.difficulty[0]

                        desc = f"[{displayed_difficulty}]({url}) {chart.level}"

                        if chart.const is not None:
                            desc += f" ({chart.const:.1f})"

                    if self.detailed and chart.charter is not None:
                        desc += f" Designer: {escape_markdown(chart.charter)}"

                    if self.detailed:
                        maxcombo = chart.maxcombo or "-"
                        tap = chart.tap or "-"
                        hold = chart.hold or "-"
                        slide = chart.slide or "-"
                        air = chart.air or "-"
                        flick = chart.flick or "-"
                        desc += f"\n**{maxcombo}** / {tap} / {hold} / {slide} / {air} / {flick}"
                    chart_level_desc.append(desc)

                if len(chart_level_desc) > 0:
                    song_description += "\n**Level**:\n"
                    if self.detailed:
                        song_description += (
                            "**CHAIN** / TAP / HOLD / SLIDE / AIR / FLICK\n\n"
                        )
                        song_description += "\n".join(chart_level_desc)
                    else:
                        song_description += " / ".join(chart_level_desc)

                embed.description = song_description
                embeds.append(embed)

            menu.clear_items()
            menu.fill_items()

            if len(page) > 0:
                menu.add_item(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label="wikiwiki",
                        url=f"https://wikiwiki.jp/chunithmwiki/{quote(page[0].wikiwiki_title or page[0].title)}",
                        row=1,
                    )
                )

                if page[0].chunirec_id is not None:
                    menu.add_item(
                        discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label="chunirec",
                            url=f"https://db.chunirec.net/music/{page[0].chunirec_id}",
                            row=1,
                        )
                    )

        return {"embeds": embeds}


class SongInfoPaginationView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        items: list[Song],
        *,
        detailed: bool = False,
    ):
        super().__init__(ctx, SongInfoPageSource(items, detailed=detailed))
