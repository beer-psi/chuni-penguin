from typing import TYPE_CHECKING, Any, Sequence, override

import discord
from discord.ext.commands import Context
from discord.utils import escape_markdown
from sqlalchemy import Row, desc, func, select

from chunithm_net.models.enums import Difficulty
from cogs.gaming._session import GuessingGameType
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
        self.game_type: GuessingGameType | None = None

    @override
    async def get_page(self, page_number: int) -> Sequence[Row[tuple[int, int]]]:  # pyright: ignore[reportIncompatibleMethodOverride]
        difficulty = self.entries[page_number]

        async with self.bot.begin_db_session() as session:
            if difficulty is not None and self.game_type is not None:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        GuessScore.score.label("score"),
                    )
                    .where(
                        (GuessScore.guild_id == self.guild_id)
                        & (GuessScore.difficulty == difficulty.value)
                        & (GuessScore.game_type == self.game_type.value)
                    )
                    .order_by(desc("score"))
                    .limit(10)
                )
            else:
                stmt = select(
                    GuessScore.discord_id.label("discord_id"),
                    func.sum(GuessScore.score).label("score"),
                ).where(GuessScore.guild_id == self.guild_id)

                if difficulty is not None:
                    stmt = stmt.where(GuessScore.difficulty == difficulty.value)
                elif self.game_type is not None:
                    stmt = stmt.where(GuessScore.game_type == self.game_type.value)

                stmt = (
                    stmt.order_by(desc("score"))
                    .group_by(GuessScore.discord_id)
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
        assert ctx.guild is not None

        # since the super `self.source` is just a PageSourceProtocol, and we want
        # typed access to the actual source without ugly casting
        self._source = GuessLeaderboardPageSource(ctx.bot, ctx.guild.id, ctx.guild.name)

        super().__init__(ctx, self._source)
        self.add_item(self.game_type_all)
        self.add_item(self.game_type_image)
        self.add_item(self.game_type_audio)
        self.add_item(self.game_type_voice)

    @discord.ui.button(label="All", row=2, style=discord.ButtonStyle.green)
    async def game_type_all(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(interaction, button, None)

    @discord.ui.button(label=GuessingGameType.IMAGE.value, row=2)
    async def game_type_image(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(interaction, button, GuessingGameType.IMAGE)

    @discord.ui.button(label=GuessingGameType.VOICE_MESSAGE.value, row=2)
    async def game_type_audio(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(
            interaction, button, GuessingGameType.VOICE_MESSAGE
        )

    @discord.ui.button(label=GuessingGameType.VOICE_CHANNEL.value, row=2)
    async def game_type_voice(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_game_type(
            interaction, button, GuessingGameType.VOICE_CHANNEL
        )

    async def _switch_game_type(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
        game_type: GuessingGameType | None,
    ):
        await interaction.response.defer()

        self._source.game_type = game_type

        self.game_type_all.style = discord.ButtonStyle.secondary
        self.game_type_image.style = discord.ButtonStyle.secondary
        self.game_type_audio.style = discord.ButtonStyle.secondary
        self.game_type_voice.style = discord.ButtonStyle.secondary

        button.style = discord.ButtonStyle.green

        await self.show_page(interaction, 0)
