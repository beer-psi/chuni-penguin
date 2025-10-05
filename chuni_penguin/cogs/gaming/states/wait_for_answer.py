import asyncio
import io
import time
from typing import TYPE_CHECKING, override

from chuni_penguin.cogs.botutils import CachedAlias
from chuni_penguin.database.models import Song

from .base import GuessingGameSkippableState, GuessingGameState
from .show_answer import ShowAnswerState

if TYPE_CHECKING:
    from chuni_penguin.cogs.gaming._session import GuessingGameSession


class WaitForAnswerState(GuessingGameSkippableState):
    def __init__(
        self,
        session: "GuessingGameSession",
        *,
        song: Song,
        aliases: list[CachedAlias],
        answer_image: io.BufferedIOBase,
        stop_music_task: asyncio.Task[None] | None = None,
    ) -> None:
        self.session = session

        self.song = song
        self.aliases = aliases
        self.answer_image = answer_image
        self._stop_music_task = stop_music_task

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        try:
            self._task = self.session.create_wait_for_answer_task(self.aliases)

            start_time = time.perf_counter_ns()
            msg = await self._task
            end_time = time.perf_counter_ns()

            guess_time = (end_time - start_time) / 1_000_000_000
            self.session.questions_timed_out = 0

            return ShowAnswerState(
                self.session,
                self.song,
                self.aliases,
                self.answer_image,
                msg,
                guess_time,
            )
        except asyncio.CancelledError:
            self.session.wrong_answers += 1
            self.session.questions_timed_out = 0

            return ShowAnswerState(
                self.session,
                self.song,
                self.aliases,
                self.answer_image,
                None,
                skipped=True,
            )
        except TimeoutError:
            if self.session.last_question_was_answered:
                self.session.wrong_answers += 1
                self.session.questions_timed_out = 0
            else:
                self.session.questions_timed_out += 1

            return ShowAnswerState(
                self.session,
                self.song,
                self.aliases,
                self.answer_image,
                None,
                timed_out=True,
            )
        finally:
            if self._stop_music_task is not None:
                self._stop_music_task.cancel()

            if self.session.voice_client is not None:
                self.session.voice_client.stop()

            self.session.questions_done += 1

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()
