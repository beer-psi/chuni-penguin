import io
from typing import TYPE_CHECKING, override

import discord
import rapidfuzz
from discord.utils import escape_markdown
from rapidfuzz import fuzz

from cogs.botutils import CachedAlias
from database.models import Song

from .base import GuessingGameState
from .end_game import (
    EndGameReachedQuestionLimit,
    EndGameReachedScoreLimit,
    EndGameTimedOut,
    EndGameTooManyWrongAnswers,
    EndGameUserCanceled,
    EndGameVoiceDisconnected,
)
from .wait import WaitState

if TYPE_CHECKING:
    from cogs.gaming._session import GuessingGameSession


class ShowAnswerState(GuessingGameState):
    def __init__(
        self,
        session: "GuessingGameSession",
        song: Song,
        aliases: list[CachedAlias],
        answer_image: io.BufferedIOBase,
        accepted_answer: discord.Message | None,
        guess_time: float | None = None,
        *,
        timed_out: bool = False,
        skipped: bool = False,
    ) -> None:
        self.session = session
        self.song = song
        self.aliases = aliases
        self.answer_image = answer_image
        self.accepted_answer = accepted_answer
        self.guess_time = guess_time
        self.timed_out = timed_out
        self.skipped = skipped

    @override
    async def __call__(self) -> "GuessingGameState | None":
        from cogs.gaming._session import GuessingGameType

        if self.accepted_answer is not None:
            accepted_user = self.accepted_answer.author

            await self.accepted_answer.add_reaction("✅")
            await self.session.increment_score(accepted_user.id)

            if accepted_user.id not in self.session.scores:
                self.session.scores[accepted_user.id] = 1
            else:
                self.session.scores[accepted_user.id] += 1

            content_lower = self.accepted_answer.content.lower()
            (_, accuracy, _) = rapidfuzz.process.extractOne(
                content_lower,
                [alias.alias for alias in self.aliases],
                scorer=fuzz.QRatio,
            )

            content = (
                f"{accepted_user.mention} has the correct answer ({accuracy:.2f}%)!"
            )
            color = discord.Color.green()
        elif self.timed_out:
            content = "Time's up!"
            color = discord.Color.red()
        elif self.skipped:
            content = "Skipped!"
            color = discord.Color.red()
        else:
            content = "Unknown reason."
            color = discord.Color.red()

        description_parts = [f"**Answer**: {escape_markdown(self.song.title)}\n"]

        if len(self.song.aliases) > 0:
            description_parts.append(
                f"-# {' / '.join([escape_markdown(x.alias) for x in self.song.aliases])}\n"
            )

        description_parts.append("\n")
        description_parts.append(f"**Artist**: {escape_markdown(self.song.artist)}\n")
        description_parts.append(f"**Category**: {escape_markdown(self.song.genre)}")

        embed = discord.Embed(
            color=color,
            description="".join(description_parts),
        )
        embed.set_image(url="attachment://image.png")

        if self.guess_time is not None:
            embed.set_footer(text=f"Guessed in {self.guess_time:.2f} seconds")

        if self.session.stopped_by:
            next_state = EndGameUserCanceled(self.session)
        elif (
            self.session.game_type == GuessingGameType.VOICE_CHANNEL
            and self.session.voice_client is None
        ):
            next_state = EndGameVoiceDisconnected(self.session)
        elif self.session.check_score_limit_reached():
            next_state = EndGameReachedScoreLimit(self.session)
        elif self.session.check_question_limit_reached():
            next_state = EndGameReachedQuestionLimit(self.session)
        elif self.session.check_wrong_answers_limit_reached():
            next_state = EndGameTooManyWrongAnswers(self.session)
        elif self.session.questions_timed_out >= 3:
            next_state = EndGameTimedOut(self.session, 3)
        else:
            content += " Next question in 3 seconds..."
            next_state = WaitState(
                self.session, 3, self.session.question_state_cls(self.session)
            )

        await self.session.channel.send(
            content=content,
            embed=embed,
            file=discord.File(self.answer_image, "image.png"),
        )
        self.answer_image.close()

        return next_state
