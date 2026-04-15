from typing import TYPE_CHECKING, override

import discord

from .base import GuessingGameState
from .wait import WaitState

if TYPE_CHECKING:
    from chuni_penguin.cogs.gaming._session import GuessingGameSession


class StartState(GuessingGameState):
    __slots__ = ("session",)

    def __init__(self, session: "GuessingGameSession") -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        from chuni_penguin.cogs.gaming._session import GuessingGameType

        embed = discord.Embed(
            color=discord.Color.yellow(),
            title="A new game is starting in 5 seconds!",
        )

        if not self.session.counts_towards_leaderboard:
            embed.description = "**This game will not count towards the leaderboard!**"

        embed.add_field(
            name="Started by", value=self.session.ctx.author.mention, inline=True
        )
        embed.add_field(
            name="Game type", value=self.session.game_type.value, inline=True
        )

        if self.session.game_type != GuessingGameType.CHARACTER_AGE:
            embed.add_field(
                name="Difficulty", value=str(self.session.difficulty), inline=True
            )

        embed.add_field(
            name="Time to answer",
            value=str(self.session.time_per_question),
            inline=True,
        )
        embed.set_footer(
            text=f"Tip: You can use {self.session.ctx.clean_prefix}skip to skip the waiting time!"
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

        if (
            self.session.genres is not None
            and self.session.game_type != GuessingGameType.CHARACTER_AGE
        ):
            embed.add_field(
                name="Genres", value=", ".join([str(g) for g in self.session.genres])
            )

        if (
            self.session.levels is not None
            and self.session.game_type != GuessingGameType.CHARACTER_AGE
        ):
            embed.add_field(
                name="Levels",
                value=", ".join([str(level) for level in self.session.levels]),
            )

        if self.session.seeded:
            embed.add_field(name="Seed", value=self.session.seed)

        await self.session.ctx.send(embed=embed)
        return WaitState(self.session, 5, self.session.question_state_cls(self.session))
