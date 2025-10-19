import asyncio
import io
import operator
import random
import traceback
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from enum import Enum
from functools import reduce
from typing import TYPE_CHECKING, Any, cast

import discord
import rapidfuzz
import sqlalchemy
from discord.ext import songbird
from discord.ext.commands import Context
from PIL import Image, ImageDraw, ImageOps
from rapidfuzz import fuzz
from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import contains_eager
from sqlalchemy.sql import update

from chuni_penguin.cogs.botutils import CachedAlias
from chuni_penguin.cogs.events import EventsCog
from chuni_penguin.constants import ASSETS_DIR
from chuni_penguin.converters import Level, LevelRange
from chuni_penguin.database import Alias, Chart, GuessScore, Song
from chuni_penguin.logging import logger
from chuni_penguin.networks.types import Difficulty, Genre
from chuni_penguin.oggopus import crop_audio, get_audio_duration

from .states.base import GuessingGameSkippableState, GuessingGameState
from .states.image import AskImageQuestionState
from .states.start import StartState
from .states.voice_call import AskVoiceCallQuestionState
from .states.voice_message import AskVoiceMessageQuestionState

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class GuessingGameType(Enum):
    IMAGE = "Jacket"
    VOICE_MESSAGE = "Audio"
    VOICE_CHANNEL = "Voice"

    def question_state_cls(self):
        if self == GuessingGameType.IMAGE:
            return AskImageQuestionState

        if self == GuessingGameType.VOICE_MESSAGE:
            return AskVoiceMessageQuestionState

        if self == GuessingGameType.VOICE_CHANNEL:
            return AskVoiceCallQuestionState

        msg = "Unknown game mode"
        raise ValueError(msg)


class GuessingGameSession:
    def __init__(
        self,
        ctx: Context["ChuniBot"],
        *,
        difficulty: Difficulty = Difficulty.basic,
        game_type: GuessingGameType = GuessingGameType.IMAGE,
        question_count: int | None = None,
        score_limit: int | None = None,
        time_per_question: int = 20,
        wrong_answers_limit: int | None = None,
        hardcore_mode: bool = False,
        genres: list[Genre] | None = None,
        levels: list[Level | LevelRange] | None = None,
        volume: int = 15,
        seed: str | None = None,
    ) -> None:
        self.ctx: Context = ctx

        if question_count is None and score_limit is None:
            msg = "Must specify either the number of questions (best of x) or the score limit (first to x)."
            raise ValueError(msg)

        self.difficulty: Difficulty = difficulty

        self._game_type: GuessingGameType = game_type
        self._question_state_cls = self._game_type.question_state_cls()

        self.questions_done: int = 0
        self.questions_timed_out: int = 0
        self.question_count: int | None = question_count

        self.score_limit: int | None = score_limit
        self.scores: dict[int, int] = {}

        self.wrong_answers_limit: int | None = wrong_answers_limit
        self.wrong_answers: int = 0

        self.time_per_question: int = time_per_question

        self.hardcore_mode: bool = hardcore_mode
        self._hardcore_mode_ignores: set[int] = set()

        self.genres: list[Genre] | None = genres
        self.levels: list[Level | LevelRange] | None = levels

        # If stopped by the bot itself, it means that we're restarting.
        self.stopped_by: discord.User | discord.Member | discord.ClientUser | None = (
            None
        )

        self.last_question_was_answered: bool = False

        self.volume: int = volume

        self.seeded: bool = seed is not None
        self.seed: str = (
            seed
            if seed is not None
            else "".join(
                random.choice("ABCDEFGHIJKLMNPQRSTUVWXYZ123456789") for _ in range(8)
            )
        )
        self.random: random.Random = random.Random(self.seed)
        self._song_ids: Sequence[int] = []

        self._tasks: set[asyncio.Task] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._current_state: GuessingGameState | None = StartState(self)

    @property
    def game_type(self) -> GuessingGameType:
        return self._game_type

    @game_type.setter
    def game_type(self, value: GuessingGameType):
        self._game_type = value
        self._question_state_cls = value.question_state_cls()

    @property
    def question_state_cls(self):
        return self._question_state_cls

    @property
    def bot(self) -> "ChuniBot":
        return self.ctx.bot

    @property
    def channel(self):
        return self.ctx.channel

    @property
    def voice_client(self):
        return cast(songbird.SongbirdClient | None, self.ctx.voice_client)

    @property
    def counts_towards_leaderboard(self):
        return self.genres is None and self.levels is None and not self.seeded

    async def run(
        self,
        after: Callable[[Exception | None], Awaitable[Any]] | None = None,
    ):
        condition = (Song.genre != "WORLD'S END") & (Song.removed == False)  # noqa: E712

        if self.genres is not None:
            condition &= Song.chunithm_catcode.in_([g.value for g in self.genres])

        if self.levels is not None:
            level_conditions: list[ColumnElement[bool]] = []

            for level in self.levels:
                if isinstance(level, LevelRange):
                    min_level, max_level = level
                    lower_range_cond = sqlalchemy.true()
                    upper_range_cond = sqlalchemy.true()

                    if min_level is not None:
                        lower_range_cond = Chart.const >= (
                            min_level.const or min_level.inferred_const
                        )
                    if max_level is not None:
                        upper_range_cond = Chart.const <= (
                            max_level.const or max_level.inferred_const
                        )

                    level_conditions.append(lower_range_cond & upper_range_cond)
                elif level.const is not None:
                    level_conditions.append(Chart.const == level.const)
                else:
                    level_conditions.append(Chart.level == level.level)

            condition &= reduce(operator.or_, level_conditions)

        async with self.bot.begin_db_session() as session:
            stmt = select(Song.id).where(condition)

            if self.levels is not None:
                stmt = stmt.join(Chart, Song.id == Chart.song_id).group_by(Song.id)

            self._song_ids = (await session.execute(stmt)).scalars().unique().all()

        state = self._current_state

        while state is not None:
            async with self._lock:
                self._current_state = state

            try:
                next_state = await state()

                if next_state is None:
                    async with self._lock:
                        self._current_state = None

                    if after is not None:
                        await after(None)

                    if self.voice_client is not None:
                        await self.voice_client.disconnect()

                    break

                state = next_state
            except Exception as e:  # noqa: BLE001
                await logger.aexception(
                    "Error running guessing game",
                    tag="guessing_game_error",
                    exc_info=e,
                )

                async with self._lock:
                    self._current_state = None

                if after is not None:
                    await after(e)

                if self.voice_client is not None:
                    await self.voice_client.disconnect()

                if events_cog := self.ctx.bot.get_cog("Events"):
                    assert isinstance(events_cog, EventsCog)
                    await events_cog._submit_error_to_webhook(self.ctx, e)

                embed = discord.Embed(
                    color=discord.Color.red(),
                    title="Game ended",
                    description=(
                        "The game ended due to an error:\n"
                        "```python\n"
                        f"{''.join(traceback.format_exception_only(e))}\n"
                        "```\n"
                        "If this keeps happening, please ping the owner or contact them in the support Discord."
                    ),
                )
                await self.channel.send(embed=embed)

                break

    async def skip(self):
        async with self._lock:
            if isinstance(self._current_state, GuessingGameSkippableState):
                await self._current_state.skip()

    async def stop(
        self, stopped_by: discord.User | discord.Member | discord.ClientUser
    ):
        async with self._lock:
            self.stopped_by = stopped_by

            if isinstance(self._current_state, GuessingGameSkippableState):
                await self._current_state.skip()

    def get_crop_dimensions(self):
        if self.difficulty == Difficulty.basic:
            return (90, 90)
        if self.difficulty in {Difficulty.advanced, Difficulty.expert}:
            return (75, 75)

        return (60, 60)

    def get_audio_length(self):
        if self.difficulty == Difficulty.basic:
            return 15
        if self.difficulty == Difficulty.advanced:
            return 10
        if self.difficulty == Difficulty.expert:
            return 7
        if self.difficulty == Difficulty.master:
            return 4

        return 1

    async def _get_random_song(self):
        if self.ctx.guild is not None:
            alias_guild_ids = [-1, self.ctx.guild.id]
        else:
            alias_guild_ids = [-1]

        song_id = self.random.choice(self._song_ids)

        async with self.bot.begin_db_session() as session:
            stmt = (
                select(Song)
                .where(Song.id == song_id)
                .outerjoin(
                    Alias,
                    (Alias.song_id == Song.id) & (Alias.guild_id.in_(alias_guild_ids)),
                )
                .options(contains_eager(Song.aliases))
            )
            song = (await session.execute(stmt)).scalars().unique().one()

            aliases = [
                CachedAlias(
                    id=None,
                    alias=song.title.lower(),
                    title=song.title,
                    song_id=song.id,
                    guild_id=None,
                )
            ]

            aliases.extend(
                [
                    CachedAlias(
                        id=alias.rowid,
                        alias=alias.alias.lower(),
                        title=song.title,
                        song_id=song.id,
                        guild_id=alias.guild_id,
                    )
                    for alias in song.aliases
                ]
            )

        return song, aliases

    async def get_image_question(self):
        # DANGER: this loops indefinitely if there are no assets filled. Consider
        # checking the assets for available audio/jackets instead of randomly
        # rolling songs and then checking afterwards.
        while True:
            song, aliases = await self._get_random_song()

            jacket_path = ASSETS_DIR / "jackets" / f"{song.id}.png"

            if not jacket_path.exists():
                await logger.awarning(
                    "Missing jacket file",
                    tag="missing_jacket_asset",
                    song_id=song.id,
                    song_title=song.title,
                    song_artist=song.artist,
                )
                continue

            break

        crop_width, crop_height = self.get_crop_dimensions()

        with Image.open(jacket_path) as img:
            x = self.random.randrange(0, img.width - crop_width)
            y = self.random.randrange(0, img.height - crop_height)

            img = img.crop((x, y, x + crop_width, y + crop_height))

            if self.difficulty in {
                Difficulty.expert,
                Difficulty.master,
                Difficulty.ultima,
            }:
                rotation = self.random.randrange(0, 4)
                img = img.rotate(90 * rotation)

            if self.difficulty == Difficulty.ultima:
                should_invert = self.random.random() < 0.5

                if should_invert:
                    img = ImageOps.invert(img.convert("RGB"))

            cropped_image_buffer = io.BytesIO()
            img.save(cropped_image_buffer, format="PNG", compress_level=3)
            cropped_image_buffer.seek(0)

        with Image.open(jacket_path) as img:
            draw = ImageDraw.Draw(img)
            draw.rectangle(
                (x, y, x + crop_width, y + crop_height),
                fill=None,
                outline=(255, 0, 0),
                width=3,
            )

            answer_image_buffer = io.BytesIO()
            img.save(answer_image_buffer, format="PNG", compress_level=3)
            answer_image_buffer.seek(0)

        return song, aliases, answer_image_buffer, cropped_image_buffer

    async def get_voice_question(self):
        # DANGER: this loops indefinitely if there are no assets filled. Consider
        # checking the assets for available audio/jackets instead of randomly
        # rolling songs and then checking afterwards.
        while True:
            song, aliases = await self._get_random_song()

            if song.bpm is None:
                await logger.awarning(
                    "Song missing BPM data",
                    tag="song_missing_bpm_data",
                    song_id=song.id,
                    song_title=song.title,
                    song_artist=song.artist,
                )
                continue

            audio_path = ASSETS_DIR / "audio" / f"{song.id}.ogg"
            jacket_path = ASSETS_DIR / "jackets" / f"{song.id}.png"

            if not audio_path.exists() or not jacket_path.exists():
                await logger.awarning(
                    "Missing audio file or jacket file",
                    tag="missing_audio_or_jacket_asset",
                    song_id=song.id,
                    song_title=song.title,
                    song_artist=song.artist,
                )
                continue

            audio_duration = int(
                await asyncio.to_thread(get_audio_duration, audio_path)
            )

            break

        # TODO: Implement the rest of the logic
        # - optionally apply filters for upper difficulties(?)
        audio_length = self.get_audio_length()

        # Usually, the first measure of game audio will be silent. Silent audio sucks, especially
        # on games where the audio is shorter, so we guard against the most basic of them first.
        audio_start = max(
            self.random.randrange(0, audio_duration - audio_length),
            60 / (song.bpm / 4),
        )

        return (
            song,
            aliases,
            jacket_path.open("rb"),
            audio_path,
            audio_start,
            audio_length,
        )

    async def get_voice_message_question(self):
        (
            song,
            aliases,
            jacket_art,
            audio_path,
            audio_start,
            audio_length,
        ) = await self.get_voice_question()

        output = io.BytesIO()

        await asyncio.to_thread(
            crop_audio, audio_path, audio_start, audio_length, output
        )
        output.seek(0)  # this is in-memory, should be fine being sync

        return (song, aliases, output, jacket_art)

    def check_score_limit_reached(self):
        if self.score_limit is None:
            return False

        if len(self.scores) == 0:
            return False

        return max(self.scores.values()) >= self.score_limit

    def check_question_limit_reached(self):
        if self.question_count is None:
            return False

        return self.questions_done >= self.question_count

    def check_wrong_answers_limit_reached(self):
        if self.wrong_answers_limit is None:
            return False

        return self.wrong_answers >= self.wrong_answers_limit

    def format_life(self):
        if self.wrong_answers_limit is None:
            return None

        return f"{self.wrong_answers_limit - self.wrong_answers}/{self.wrong_answers_limit}"

    async def increment_score(self, user_id: int):
        if not self.counts_towards_leaderboard:
            return

        guild_id = self.ctx.guild.id if self.ctx.guild else -1

        async with self.bot.begin_db_session() as session, session.begin():
            stmt = insert(GuessScore).values(
                discord_id=user_id,
                guild_id=guild_id,
                difficulty=self.difficulty.value,
                game_type=self.game_type.value,
                score=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    GuessScore.discord_id,
                    GuessScore.guild_id,
                    GuessScore.difficulty,
                    GuessScore.game_type,
                ],
                set_={"score": GuessScore.score + 1},
            )

            await session.execute(stmt)
            await session.commit()

    async def increment_alias_uses(self, alias_id: int):
        async with self.bot.begin_db_session() as session, session.begin():
            stmt = (
                update(Alias).where(Alias.rowid == alias_id).values(uses=Alias.uses + 1)
            )

            await session.execute(stmt)
            await session.commit()

    def print_score_list(self):
        if len(self.scores) == 0:
            return "No one got any points."

        score_list = ""

        for user_id, score in sorted(
            self.scores.items(), key=lambda item: item[1], reverse=True
        ):
            score_list += f"<@{user_id}> has {score} point"

            if score != 1:
                score_list += "s"

            score_list += "\n"

        return score_list

    def create_wait_for_answer_task(self, aliases: list[CachedAlias]):
        self.last_question_was_answered = False
        self._hardcore_mode_ignores.clear()

        def on_typing_check(
            channel: discord.TextChannel | discord.GroupChannel | discord.DMChannel,
            _user: discord.User | discord.Member,
            _when: datetime,
        ):
            if channel.id == self.channel.id:
                self.last_question_was_answered = True
                return True

            return False

        def on_message_check(m: discord.Message):
            if m.author.id in self._hardcore_mode_ignores:
                return False

            if not self.last_question_was_answered and m.channel == self.channel:
                self.last_question_was_answered = True

            if m.channel != self.channel:
                return False

            content_lower = m.content.lower()

            result = rapidfuzz.process.extractOne(
                content_lower,
                [alias.alias for alias in aliases],
                scorer=fuzz.QRatio,
                score_cutoff=80,
            )
            is_correct_answer = result is not None

            if not is_correct_answer and self.hardcore_mode:
                reaction_task = asyncio.create_task(m.add_reaction("❌"))

                self._tasks.add(reaction_task)
                reaction_task.add_done_callback(self._tasks.discard)

                self._hardcore_mode_ignores.add(m.author.id)

            if is_correct_answer:
                alias = aliases[result[2]]

                if alias.id is not None:
                    update_uses_task = asyncio.create_task(
                        self.increment_alias_uses(alias.id)
                    )

                    self._tasks.add(update_uses_task)
                    update_uses_task.add_done_callback(self._tasks.discard)

            return is_correct_answer

        async def wait_for_typing_wrapper():
            try:
                return await self.bot.wait_for(
                    "typing", check=on_typing_check, timeout=self.time_per_question
                )
            except asyncio.TimeoutError:
                pass

        typing_task = asyncio.create_task(wait_for_typing_wrapper())

        self._tasks.add(typing_task)
        typing_task.add_done_callback(self._tasks.discard)

        return asyncio.create_task(
            self.bot.wait_for(
                "message", check=on_message_check, timeout=self.time_per_question
            )
        )
