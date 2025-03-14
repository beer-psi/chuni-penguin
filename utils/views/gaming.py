from asyncio import Task
from types import SimpleNamespace
from typing import TYPE_CHECKING, override

import discord
from discord.channel import CategoryChannel, ForumChannel
from discord.enums import ButtonStyle
from discord.ext.commands import Context
from discord.ext.commands.context import DeferTyping
from discord.interactions import Interaction
from discord.message import Message
from discord.ui import Button, View, button
from discord.utils import escape_markdown
from sqlalchemy import desc, func, select

from chunithm_net.models.enums import Difficulty
from database.models import GuessScore

from ._pagination import PaginationView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.gaming import GamingCog


class SkipButtonView(View):
    task: Task
    message: Message

    def __init__(self):
        super().__init__(timeout=20)

    async def on_timeout(self):
        self.clear_items()
        await self.message.edit(view=self)

    @button(label="⏩", style=ButtonStyle.danger)
    async def skip(self, interaction: Interaction, _: Button):
        await interaction.response.defer()
        await self.on_timeout()
        self.task.cancel()


class NextGameButtonView(View):
    def __init__(self, cog: "GamingCog", sessions: dict[int, Task]):
        super().__init__(timeout=None)
        self.cog = cog
        self.sessions = sessions

    @button(label="New game", style=ButtonStyle.green, custom_id="new_guess_game")
    async def new_game(self, interaction: Interaction, button: Button):
        if (
            isinstance(interaction.channel, (ForumChannel, CategoryChannel))
            or interaction.channel_id in self.sessions
            or interaction.channel is None
        ):
            return await interaction.response.defer()

        cursed_context = SimpleNamespace()

        # The class only calls .defer, which interaction.response also has.
        cursed_context.typing = lambda: DeferTyping(
            interaction.response, ephemeral=True
        )  # type: ignore[reportGeneralTypeIssues]

        cursed_context.author = interaction.user
        cursed_context.guild = interaction.guild
        cursed_context.channel = interaction.channel
        cursed_context.reply = interaction.channel.send
        cursed_context.send = interaction.channel.send

        # This has all the functions that guess() needs.
        await self.cog.guess(cursed_context)  # type: ignore[reportGeneralTypeIssues]
        return None


class GuessLeaderboardView(PaginationView):
    def __init__(self, ctx: Context):
        super().__init__(
            ctx,
            items=[
                None,
                Difficulty.BASIC,
                Difficulty.ADVANCED,
                Difficulty.EXPERT,
                Difficulty.MASTER,
                Difficulty.ULTIMA,
            ],
            per_page=1,
        )

    async def format_page(self, difficulty: Difficulty | None = None):
        bot: "ChuniBot" = self.ctx.bot

        async with bot.begin_db_session() as session:
            if difficulty is None:
                stmt = (
                    select(
                        GuessScore.discord_id.label("discord_id"),
                        func.sum(GuessScore.score).label("score"),
                    )
                    .where(GuessScore.guild_id == self.ctx.guild.id)
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
                        (GuessScore.guild_id == self.ctx.guild.id)
                        & (GuessScore.difficulty == difficulty.value)
                    )
                    .order_by(desc("score"))
                    .limit(10)
                )

            scores = (await session.execute(stmt)).fetchall()

            title = f"Guess Leaderboard for {escape_markdown(self.ctx.guild.name)}"

            if difficulty is not None:
                title += f" [{difficulty}]"

            description = ""

            for idx, score in enumerate(scores):
                description += f"\u200b{idx + 1}. <@{score[0]}>: {score[1]}\n"

            embed = discord.Embed(
                color=discord.Color.yellow()
                if difficulty is None
                else difficulty.color(),
                title=title,
                description=description,
            )

        return [embed]

    @override
    async def callback(self, interaction: discord.Interaction):
        difficulty: Difficulty | None = self.items[self.page]

        await interaction.response.edit_message(
            embeds=await self.format_page(difficulty),
            view=self,
        )
