from typing import override

import discord

from cogs.gaming._session import GuessingGameSession

from .base import GuessingGameState
from .wait import WaitState


class StartState(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        embed = discord.Embed(
            color=discord.Color.yellow(),
            title="A new game is starting in 5 seconds!",
        )
        embed.add_field(
            name="Started by", value=self.session.ctx.author.mention, inline=True
        )
        embed.add_field(
            name="Game type", value=self.session.game_type.value, inline=True
        )
        embed.add_field(
            name="Difficulty", value=str(self.session.difficulty), inline=True
        )
        embed.add_field(
            name="Time to answer",
            value=str(self.session.time_per_question),
            inline=True,
        )
        embed.set_footer(
            text=f"Tip: You can use {self.session.ctx.prefix}skip to skip the waiting time!"
        )

        if self.session.question_count is not None:
            embed.add_field(
                name="Questions", value=self.session.question_count, inline=True
            )

        if self.session.score_limit is not None:
            embed.add_field(
                name="Score limit", value=self.session.score_limit, inline=True
            )

        if self.session.wrong_answers_limit is not None:
            embed.add_field(
                name="LIFE", value=self.session.wrong_answers_limit, inline=True
            )

        if self.session.hardcore_mode:
            embed.add_field(name="Hardcore mode", value="Enabled", inline=True)

        await self.session.ctx.send(embed=embed)
        return WaitState(self.session, 5, self.session.question_state(self.session))
