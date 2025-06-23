import asyncio
import io
import random
from enum import Enum
from typing import TYPE_CHECKING, cast

import discord
from discord.ext.commands import Context
from PIL import Image, ImageDraw, ImageOps
from rapidfuzz import fuzz
from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert

from chunithm_net.models.enums import Difficulty
from database.models import Alias, GuessScore, Song
from utils import json_loads
from utils.logging import logger

from ._constants import ASSETS_DIR

if TYPE_CHECKING:
    from bot import ChuniBot


class GuessingGameType(Enum):
    IMAGE = "Jacket"
    VOICE_MESSAGE = "Audio"
    VOICE_CHANNEL = "Voice"


class GuessingGameSession:
    def __init__(
        self,
        ctx: Context["ChuniBot"],
        *,
        difficulty: Difficulty = Difficulty.BASIC,
        game_type: GuessingGameType = GuessingGameType.IMAGE,
        question_count: int | None = None,
        score_limit: int | None = None,
        time_per_question: int = 20,
        wrong_answers_limit: int | None = None,
    ) -> None:
        self.ctx: Context = ctx

        if question_count is None and score_limit is None:
            msg = "Must specify either the number of questions (best of x) or the score limit (first to x)."
            raise ValueError(msg)

        self.difficulty: Difficulty = difficulty
        self.game_type: GuessingGameType = game_type

        self.questions_done: int = 0
        self.questions_timed_out: int = 0
        self.question_count: int | None = question_count

        self.score_limit: int | None = score_limit
        self.scores: dict[int, int] = {}

        self.wrong_answers_limit: int | None = wrong_answers_limit
        self.wrong_answers: int = 0

        self.time_per_question = time_per_question

        # If stopped by the bot itself, it means that we're restarting.
        self.stopped_by: discord.User | discord.Member | discord.ClientUser | None = (
            None
        )

        self.last_question_was_answered: bool = False

    @property
    def bot(self) -> "ChuniBot":
        return self.ctx.bot

    @property
    def channel(self):
        return self.ctx.channel

    @property
    def voice_client(self):
        return cast(discord.VoiceClient | None, self.ctx.voice_client)

    def get_crop_dimensions(self):
        if self.difficulty == Difficulty.BASIC:
            return (90, 90)
        if self.difficulty in {Difficulty.ADVANCED, Difficulty.EXPERT}:
            return (75, 75)

        return (60, 60)

    def get_audio_length(self):
        if self.difficulty == Difficulty.BASIC:
            return 15
        if self.difficulty == Difficulty.ADVANCED:
            return 10
        if self.difficulty == Difficulty.EXPERT:
            return 7
        if self.difficulty == Difficulty.MASTER:
            return 4

        return 1

    async def get_image_question(self):
        async with self.bot.begin_db_session() as session:
            while True:
                stmt = (
                    select(Song)
                    .where((Song.genre != "WORLD'S END") & (Song.removed == False))  # noqa: E712
                    .order_by(text("RANDOM()"))
                    .limit(1)
                )
                song = (await session.execute(stmt)).scalar_one()

                stmt = select(Alias).where(
                    (Alias.song_id == song.id)
                    & (
                        (Alias.guild_id == -1)
                        | (
                            Alias.guild_id
                            == (self.ctx.guild.id if self.ctx.guild is not None else -1)
                        )
                    )
                )
                aliases = [song.title] + [
                    alias.alias for alias in (await session.execute(stmt)).scalars()
                ]

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
            x = random.randrange(0, img.width - crop_width)
            y = random.randrange(0, img.height - crop_height)

            img = img.crop((x, y, x + crop_width, y + crop_height))

            if self.difficulty in {
                Difficulty.EXPERT,
                Difficulty.MASTER,
                Difficulty.ULTIMA,
            }:
                rotation = random.randrange(0, 4)
                img = img.rotate(90 * rotation)

            if self.difficulty == Difficulty.ULTIMA:
                should_invert = random.random() < 0.5

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

    async def get_voice_message_question(self):
        async with self.bot.begin_db_session() as session:
            while True:
                stmt = (
                    select(Song)
                    .where((Song.genre != "WORLD'S END") & (Song.removed == False))  # noqa: E712
                    .order_by(text("RANDOM()"))
                    .limit(1)
                )
                song = (await session.execute(stmt)).scalar_one()

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

                ffprobe_process = await asyncio.subprocess.create_subprocess_exec(
                    "ffprobe",
                    "-i",
                    str(audio_path),
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_error",
                    "-loglevel",
                    "fatal",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await ffprobe_process.communicate()
                ffprobe_data = json_loads(stdout)

                if "error" in ffprobe_data:
                    await logger.awarning(
                        "Invalid audio data",
                        tag="invalid_audio_data",
                        song_id=song.id,
                        song_title=song.title,
                        song_artist=song.artist,
                        error=ffprobe_data["error"],
                    )
                    continue

                audio_duration = int(float((ffprobe_data["format"]["duration"])))

                stmt = select(Alias).where(
                    (Alias.song_id == song.id)
                    & (
                        (Alias.guild_id == -1)
                        | (
                            Alias.guild_id
                            == (self.ctx.guild.id if self.ctx.guild is not None else -1)
                        )
                    )
                )
                aliases = [song.title] + [
                    alias.alias for alias in (await session.execute(stmt)).scalars()
                ]

                break

        # TODO: Implement the rest of the logic
        # - The audio cut should not fall into silence
        # - use self.get_audio_length() to figure out the length to cut
        # - optionally apply filters for upper difficulties(?)
        audio_length = self.get_audio_length()

        # Usually, the first measure of game audio will be silent. Silent audio sucks, especially
        # on games where the audio is shorter, so we guard against the most basic of them first.
        audio_start = max(
            random.randrange(0, audio_duration - audio_length), 60 / (song.bpm / 4)
        )

        ffmpeg_process = await asyncio.subprocess.create_subprocess_exec(
            "ffmpeg",
            "-ss",
            str(audio_start),
            "-i",
            str(audio_path),
            "-t",
            str(audio_length),
            "-f",
            "ogg",
            "-acodec",
            "libopus",
            "-filter:a",
            "volume=0.15",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await ffmpeg_process.communicate()

        return (
            song,
            aliases,
            io.BytesIO(stdout),
            jacket_path.open("rb"),
        )

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

    def create_wait_for_answer_task(self, aliases: list[str]):
        self.last_question_was_answered = False

        def check(m: discord.Message):
            if not self.last_question_was_answered and m.channel == self.channel:
                self.last_question_was_answered = True

            return (
                m.channel == self.channel
                and max(
                    [
                        fuzz.QRatio(m.content, alias, processor=str.lower)
                        for alias in aliases
                    ]
                )
                >= 80
            )

        return asyncio.create_task(
            self.bot.wait_for("message", check=check, timeout=self.time_per_question)
        )

    @property
    def question_state(self):
        if self.game_type == GuessingGameType.IMAGE:
            from .states.image import AskImageQuestionState

            return AskImageQuestionState

        if self.game_type == GuessingGameType.VOICE_MESSAGE:
            from .states.voice_message import AskVoiceMessageQuestionState

            return AskVoiceMessageQuestionState

        if self.game_type == GuessingGameType.VOICE_CHANNEL:
            from .states.voice_call import AskVoiceCallQuestionState

            return AskVoiceCallQuestionState

        msg = "Unsupported gamemode"
        raise ValueError(msg)
