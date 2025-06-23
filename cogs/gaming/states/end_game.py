from typing import override

import discord

from cogs.gaming._session import GuessingGameSession

from .base import GuessingGameState


async def end_game(
    session: GuessingGameSession,
    color: discord.Color,
    description: str,
    *,
    footer: str | None = None,
    show_lives: bool = True,
):
    embed = discord.Embed(
        color=color,
        title="Game ended",
        description=description,
    )
    embed.add_field(name="Difficulty", value=str(session.difficulty))

    if show_lives and session.wrong_answers_limit:
        embed.add_field(name="LIFE", value=session.format_life())

    embed.add_field(name="Time to answer", value=session.time_per_question)

    embed.add_field(name="Final Scores", value=session.print_score_list(), inline=False)
    embed.set_footer(
        text=footer
        or f"Use `{session.ctx.prefix}guess lb` to view the server leaderboard."
    )

    await session.channel.send(embed=embed)


class EndGameTimedOut(GuessingGameState):
    def __init__(self, session: GuessingGameSession, n_unanswered: int) -> None:
        self.session = session
        self.n_unanswered = n_unanswered

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.red(),
            f"{self.n_unanswered} question{'' if self.n_unanswered == 1 else 's'} in a row went unanswered.",
            show_lives=False,
        )
        return None


class EndGameReachedQuestionLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.green(),
            "The question limit has been reached.",
        )
        return None


class EndGameReachedScoreLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.green(),
            "The score limit has been reached.",
        )
        return None


class EndGameUserCanceled(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        if session.stopped_by is None:
            msg = "Cannot reach this state if stopped_by is None."
            raise ValueError(msg)

        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        if self.session.stopped_by == self.session.bot.user:
            await end_game(
                self.session,
                discord.Color.yellow(),
                "I'm going down for an update. See you in about five minutes!",
                footer="This beer guy keeps messing with my code...",
                show_lives=False,
            )
        elif self.session.stopped_by is not None:  # this should always be true
            await end_game(
                self.session,
                discord.Color.red(),
                f"The game was stopped by {self.session.stopped_by.mention}.",
                show_lives=False,
            )

        return None


class EndGameTooManyWrongAnswers(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        if session.wrong_answers_limit is None:
            msg = "Cannot reach this state if wrong answers limit is not set."
            raise ValueError(msg)

        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        await end_game(
            self.session,
            discord.Color.red(),
            f"More than {self.session.wrong_answers_limit} question{'s' if self.session.wrong_answers_limit != 1 else ''} was answered wrongly.",
        )
        return None
