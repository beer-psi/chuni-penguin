from typing import TYPE_CHECKING, Any, Sequence, override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown
from sqlalchemy import Row, desc, func, select

from chunithm_net.models.enums import Difficulty
from database.models import GuessScore

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from bot import ChuniBot


class GuessLeaderboardPageSource(ListPageSource[Difficulty | None]):
    def __init__(self, bot: "ChuniBot", guild_id: int, guild_name: str) -> None:
        super().__init__(
            [
                None,
                Difficulty.BASIC,
                Difficulty.ADVANCED,
                Difficulty.EXPERT,
                Difficulty.MASTER,
                Difficulty.ULTIMA,
            ],
            per_page=1,
        )
        self.bot = bot
        self.guild_id = guild_id
        self.guild_name = guild_name

    @override
    async def get_page(self, page_number: int) -> Sequence[Row[tuple[int, int]]]:  # pyright: ignore[reportIncompatibleMethodOverride]
        difficulty = self.entries[page_number]

        async with self.bot.begin_db_session() as session:
            if difficulty is None:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        func.sum(GuessScore.score).label("score"),
                    )
                    .where(GuessScore.guild_id == self.guild_id)
                    .order_by(desc("score"))
                    .group_by(GuessScore.discord_id)
                    .limit(10)
                )
            else:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        GuessScore.score.label("score"),
                    )
                    .where(
                        (GuessScore.guild_id == self.guild_id)
                        & (GuessScore.difficulty == difficulty.value)
                    )
                    .order_by(desc("score"))
                    .limit(10)
                )

            return (await session.execute(stmt)).fetchall()

    @override
    async def format_page(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, menu: "PaginationView", page: Sequence[Row[tuple[int, int]]]
    ) -> dict[str, Any]:
        description = ""
        difficulty = self.entries[menu.current_page]

        title = f"Guess Leaderboard for {escape_markdown(self.guild_name)}"

        if difficulty is not None:
            title += f" [{difficulty}]"

        for idx, score in enumerate(page):
            description += f"\u200b{idx + 1}. <@{score[0]}>: {score[1]}\n"

        embed = discord.Embed(
            color=discord.Color.yellow() if difficulty is None else difficulty.color(),
            title=title,
            description=description,
        )

        return {"embed": embed}


class GuessLeaderboardView(PaginationView):
    def __init__(self, ctx: Context):
        super().__init__(
            ctx, GuessLeaderboardPageSource(ctx.bot, ctx.guild.id, ctx.guild.name)
        )
