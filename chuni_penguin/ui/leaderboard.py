import unicodedata
from collections.abc import Sequence
from typing import override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown, format_dt

from chuni_penguin.config import config
from chuni_penguin.database import Chart, Song
from chuni_penguin.types import (
    ClearLamp,
    ComboLamp,
    Difficulty,
    Leaderboard,
    LeaderboardEntry,
    LinkedGateLeaderboard,
    LinkedGateLeaderboardEntry,
    Rank,
)
from chuni_penguin.utils import get_jacket_url

from ._pagination import FormatPageReturn, ListPageSource, PaginationView
from .components.chart_card_embed import ChartCardEmbed
from .song_info import SongInfoEmbed


class LeaderboardPageSource(ListPageSource):
    __slots__ = (
        "chart",
        "difficulty",
        "leaderboard",
        "network",
        "song",
        "synthesis_alt_jacket",
    )

    def __init__(
        self,
        leaderboard: Leaderboard,
        song: Song,
        difficulty: Difficulty,
        chart: Chart | None = None,
        *,
        per_page: int,
        synthesis_alt_jacket: str | None = None,
        network: str | None = None,
    ) -> None:
        super().__init__(leaderboard.ranking, per_page=per_page)

        self.leaderboard: Leaderboard = leaderboard
        self.song: Song = song
        self.difficulty: Difficulty = difficulty
        self.chart: Chart | None = chart
        self.synthesis_alt_jacket: str | None = synthesis_alt_jacket
        self.network: str | None = network

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[LeaderboardEntry]
    ) -> FormatPageReturn:
        if self.chart is not None:
            info_embed = ChartCardEmbed(
                self.chart, synthesis_alt_jacket=self.synthesis_alt_jacket
            )
        else:
            info_embed = discord.Embed(
                description=f"**{escape_markdown(self.song.title)} [{self.difficulty}]**",
            )
            info_embed.set_thumbnail(url=get_jacket_url(self.song))

            if self.synthesis_alt_jacket == "none":
                info_embed.set_thumbnail(url=None)
            elif self.synthesis_alt_jacket != "default" and config.web.serve_assets:
                info_embed.set_thumbnail(
                    url=f"{config.web.base_url}/assets/jackets/{self.song.id}_{self.synthesis_alt_jacket}.webp"
                )

        description = ""

        try:
            max_player_name_length = max(len(record.player_name) for record in page)
            max_position_length = max(len(str(record.position)) for record in page)

        except ValueError:  # empty iterable
            description = "No scores."
        else:
            has_widechar = any(
                any(
                    unicodedata.east_asian_width(c) in ("W", "F", "A")
                    for c in record.player_name
                )
                for record in page
            )

            for record in page:
                if has_widechar:
                    description += f"`{record.position: >{max_position_length}}` {record.player_name:\u3000<{max_player_name_length}} ▸ {config.icons.rank_icon(Rank.from_score(record.score))}"
                else:
                    description += f"`{record.position: >{max_position_length}}` `{record.player_name: <{max_player_name_length}}` ▸ {config.icons.rank_icon(Rank.from_score(record.score))}"

                if record.combo_lamp is not None or record.clear_lamp is not None:
                    lamp_parts: list[str] = []

                    if (
                        record.combo_lamp is not None
                        and record.combo_lamp != ComboLamp.none
                    ):
                        lamp_parts.append(record.combo_lamp.short())

                    if (
                        record.clear_lamp is not None
                        and record.clear_lamp != ClearLamp.clear
                    ):
                        lamp_parts.append(record.clear_lamp.short())

                    # if there are no lamp parts then combo_lamp=None clear_lamp=Clear
                    if len(lamp_parts) == 0:
                        lamp_parts.append("CLR")

                    description += f" ▸ {' / '.join(lamp_parts)}"

                description += f" ▸ {record.score}"

                if record.judgements is not None:
                    description += f" ({record.judgements.justice_critical} / {record.judgements.justice} / {record.judgements.attack} / {record.judgements.miss})"

                if record.ajc_count is not None:
                    description += f" (AJC: {record.ajc_count})"

                if record.achieved_at is not None:
                    description += f" ▸ {format_dt(record.achieved_at, 'f')}\n"
                else:
                    description += "\n"

        leaderboard_embed = discord.Embed(
            color=self.difficulty.color(),
            description=description,
            timestamp=self.leaderboard.updated_at,
        )

        leaderboard_embed.set_footer(text=self.network)

        return {"embeds": [info_embed, leaderboard_embed]}


class LinkedGateLeaderboardPageSource(ListPageSource):
    __slots__ = (
        "color",
        "leaderboard",
        "network",
        "song",
        "synthesis_alt_jacket",
    )

    def __init__(
        self,
        leaderboard: LinkedGateLeaderboard,
        song: Song,
        color: discord.Color,
        *,
        per_page: int,
        synthesis_alt_jacket: str | None = None,
        network: str | None = None,
    ) -> None:
        super().__init__(leaderboard.ranking, per_page=per_page)

        self.leaderboard: LinkedGateLeaderboard = leaderboard
        self.song: Song = song
        self.color: discord.Color = color
        self.synthesis_alt_jacket: str | None = synthesis_alt_jacket
        self.network: str | None = network

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[LinkedGateLeaderboardEntry]
    ) -> FormatPageReturn:
        try:
            max_player_name_length = max(len(record.player_name) for record in page)
            max_position_length = max(len(str(record.position)) for record in page)
        except ValueError:  # empty iterable
            description = "No scores."
        else:
            has_widechar = any(
                any(
                    unicodedata.east_asian_width(c) in ("W", "F", "A")
                    for c in record.player_name
                )
                for record in page
            )
            padding_char = "\u3000" if has_widechar else " "
            description = "\n".join(
                [
                    f"`{record.position: >{max_position_length}}` {record.player_name:{padding_char}<{max_player_name_length}} ▸ {config.icons.icon(f'link_level_{record.link_level.name}', str(record.link_level))} ▸ {format_dt(record.achieved_at, 'f')}"
                    for record in page
                ]
            )

        if description == "":
            description = "No scores."

        leaderboard_embed = discord.Embed(
            color=self.color,
            description=description,
            timestamp=self.leaderboard.updated_at,
        )

        leaderboard_embed.set_footer(text=self.network)

        return {
            "embeds": [SongInfoEmbed(self.song, self.song.charts), leaderboard_embed]
        }


class LeaderboardView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        leaderboard: Leaderboard,
        song: Song,
        difficulty: Difficulty,
        chart: Chart | None = None,
        per_page: int = 10,
        synthesis_alt_jacket: str | None = None,
        network: str | None = None,
    ):
        super().__init__(
            ctx,
            LeaderboardPageSource(
                leaderboard,
                song,
                difficulty,
                chart,
                per_page=per_page,
                synthesis_alt_jacket=synthesis_alt_jacket,
                network=network,
            ),
        )


class LinkedGateLeaderboardView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        leaderboard: LinkedGateLeaderboard,
        song: Song,
        color: discord.Color,
        per_page: int = 10,
        synthesis_alt_jacket: str | None = None,
        network: str | None = None,
    ):
        super().__init__(
            ctx,
            LinkedGateLeaderboardPageSource(
                leaderboard,
                song,
                color,
                per_page=per_page,
                synthesis_alt_jacket=synthesis_alt_jacket,
                network=network,
            ),
        )
