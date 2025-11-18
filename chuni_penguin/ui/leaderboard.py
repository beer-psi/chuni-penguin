from collections.abc import Sequence
from typing import Any, override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chuni_penguin.config import config
from chuni_penguin.database import Chart, Song
from chuni_penguin.networks.types import (
    Difficulty,
    Leaderboard,
    LeaderboardEntry,
    Rank,
)
from chuni_penguin.ui import ChartCardEmbed
from chuni_penguin.utils import get_jacket_url

from ._pagination import ListPageSource, PaginationView


class LeaderboardPageSource(ListPageSource):
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
    ) -> dict[str, Any]:
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

        for record in page:
            description += f"`{record.position: >3}` {record.player_name} ▸ {config.icons.rank_icon(Rank.from_score(record.score))} ▸ {record.score}"

            if record.judgements is not None:
                description += f" ({record.judgements.justice_critical} / {record.judgements.justice} / {record.judgements.attack} / {record.judgements.miss})"

            if record.ajc_count is not None:
                description += f" (AJC: {record.ajc_count})"

            if record.achieved_at is not None:
                description += f" ▸ <t:{int(record.achieved_at.timestamp())}:f>\n"
            else:
                description += "\n"

        if description == "":
            description = "No scores."

        leaderboard_embed = discord.Embed(
            color=self.difficulty.color(),
            description=description,
            timestamp=self.leaderboard.updated_at,
        )

        leaderboard_embed.set_footer(text=self.network)

        return {"embeds": [info_embed, leaderboard_embed]}


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
