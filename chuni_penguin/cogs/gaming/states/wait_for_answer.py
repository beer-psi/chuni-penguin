import asyncio
import contextlib
import io
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, override

import discord
import rapidfuzz
from discord.ext import songbird
from rapidfuzz import fuzz

from chuni_penguin.cogs.botutils import CachedAlias
from chuni_penguin.database import Character, Song

from .base import GuessingGameSkippableState, GuessingGameState
from .show_answer import ShowAnswerState, ShowCharacterAgeAnswerState

if TYPE_CHECKING:
    from chuni_penguin.cogs.gaming._session import GuessingGameSession

INFINITY = float("inf")


def create_answer_check(session: "GuessingGameSession", aliases: list[CachedAlias]):
    def check(m: discord.Message):
        content_lower = m.content.lower()

        result = rapidfuzz.process.extractOne(
            content_lower,
            [alias.alias for alias in aliases],
            scorer=fuzz.QRatio,
            score_cutoff=80,
        )
        is_correct_answer = result is not None

        if is_correct_answer:
            alias = aliases[result[2]]

            if alias.id is not None:
                update_uses_task = asyncio.create_task(
                    session.increment_alias_uses(alias.id)
                )

                session._tasks.add(update_uses_task)
                update_uses_task.add_done_callback(session._tasks.discard)

        return is_correct_answer

    return check


def create_character_age_answer_check(
    ages: list[float],
) -> Callable[[discord.Message], bool]:
    if len(ages) < 0:
        return lambda m: False

    if ages[0] == INFINITY:
        return lambda m: m.content.lower().startswith(("inf", "immortal", "eternal"))

    ranges: list[tuple[float, float]] = []

    for age in ages:
        # numbers pulled out of my ass
        if age < 100:
            ranges.append((age * 0.95, age * 1.05))
        elif 100 <= age < 1000:
            ranges.append((age * 0.98, age * 1.02))
        else:
            ranges.append((age * 0.99, age * 1.01))

    def check(m: discord.Message):
        try:
            answer = float(m.content)
        except ValueError:
            return False

        return any(lower <= answer <= higher for lower, higher in ranges)

    return check


class WaitForAnswerState(GuessingGameSkippableState):
    __slots__ = (
        "_stop_music_task",
        "_task",
        "aliases",
        "answer_image",
        "session",
        "song",
    )

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
            self._task = self.session.create_wait_for_answer_task(
                create_answer_check(self.session, self.aliases)
            )

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
                with contextlib.suppress(songbird.ControlError):
                    self.session.voice_client.stop()

            self.session.questions_done += 1

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()


class WaitForCharacterAgeAnswerState(GuessingGameSkippableState):
    def __init__(self, session: "GuessingGameSession", *, character: Character):
        self.session = session
        self.character = character

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        try:
            self._task = self.session.create_wait_for_answer_task(
                create_character_age_answer_check(self.character.ages)  # pyright: ignore[reportArgumentType]
            )

            start_time = time.perf_counter_ns()
            msg = await self._task
            end_time = time.perf_counter_ns()

            guess_time = (end_time - start_time) / 1_000_000_000
            self.session.questions_timed_out = 0

            return ShowCharacterAgeAnswerState(
                self.session, self.character, msg, guess_time
            )
        except asyncio.CancelledError:
            self.session.wrong_answers += 1
            self.session.questions_timed_out = 0

            return ShowCharacterAgeAnswerState(
                self.session, self.character, None, skipped=True
            )
        except TimeoutError:
            if self.session.last_question_was_answered:
                self.session.wrong_answers += 1
                self.session.questions_timed_out = 0
            else:
                self.session.questions_timed_out += 1

            return ShowCharacterAgeAnswerState(
                self.session, self.character, None, timed_out=True
            )
        finally:
            self.session.questions_done += 1

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()
