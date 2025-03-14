import asyncio
import contextlib
import io
import random
import traceback
from argparse import ArgumentError
from asyncio import CancelledError, TimeoutError
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Protocol, override

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown
from PIL import Image, ImageDraw, ImageOps
from rapidfuzz import fuzz
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.sqlite import insert

from chunithm_net.models.enums import Difficulty
from database.models import Alias, GuessScore, Song
from utils import shlex_split
from utils.argparse import DiscordArguments
from utils.logging import logger as root_logger
from utils.views.gaming import GuessLeaderboardView

if TYPE_CHECKING:
    from discord.abc import MessageableChannel

    from bot import ChuniBot
    from cogs.botutils import UtilsCog

logger = root_logger.getChild(__name__)
ASSETS_DIR = Path(__file__).parent.parent / "assets"


class GuessingGameSession:
    def __init__(
        self,
        ctx: Context["ChuniBot"],
        *,
        difficulty: Difficulty = Difficulty.BASIC,
        question_count: int | None = None,
        score_limit: int | None = None,
        time_per_question: int = 20,
    ) -> None:
        self.ctx: Context = ctx

        if question_count is None and score_limit is None:
            msg = "Must specify either the number of questions (best of x) or the score limit (first to x)."
            raise ValueError(msg)

        self.difficulty: Difficulty = difficulty
        self.questions_done: int = 0
        self.questions_timed_out: int = 0
        self.question_count: int | None = question_count
        self.score_limit: int | None = score_limit
        self.scores: dict[int, int] = {}

        self.time_per_question = time_per_question

    @property
    def bot(self) -> "ChuniBot":
        return self.ctx.bot

    @property
    def channel(self):
        return self.ctx.channel

    def get_crop_dimensions(self):
        if self.difficulty == Difficulty.BASIC:
            return (90, 90)
        if self.difficulty in {Difficulty.ADVANCED, Difficulty.EXPERT}:
            return (75, 75)

        return (60, 60)

    async def get_question(self):
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
                    logger.warning(
                        "Missing jacket file for existing song %s - %s (ID %s)",
                        song.artist,
                        song.title,
                        song.id,
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

    def check_score_limit_reached(self):
        if self.score_limit is None:
            return False

        return max(self.scores.values()) >= self.score_limit

    def check_question_limit_reached(self):
        if self.question_count is None:
            return False

        return self.questions_done >= self.question_count

    async def increment_score(self, user_id: int):
        guild_id = self.ctx.guild.id if self.ctx.guild else -1

        async with self.bot.begin_db_session() as session, session.begin():
            stmt = insert(GuessScore).values(
                discord_id=user_id,
                guild_id=guild_id,
                difficulty=self.difficulty.value,
                score=1,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    GuessScore.discord_id,
                    GuessScore.guild_id,
                    GuessScore.difficulty,
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


class GuessingGameState(Protocol):
    async def __call__(self) -> "GuessingGameState | None":
        """Execute the current state.

        It must return another state for the executor to run, or return None
        to finish the state machine.
        """
        ...


class GuessingGameSkippableState(GuessingGameState):
    async def skip(self):
        """Skips the current state."""


class WaitState(GuessingGameSkippableState):
    def __init__(
        self,
        session: GuessingGameSession,
        wait_time_s: int,
        next_state: GuessingGameState,
    ):
        self.session = session
        self.wait_time_s = wait_time_s
        self.next_state = next_state

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        self._task = asyncio.create_task(asyncio.sleep(self.wait_time_s))

        with contextlib.suppress(CancelledError):
            await self._task

        return self.next_state

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()


class EndGameTimedOut(GuessingGameState):
    def __init__(self, session: GuessingGameSession, n_unanswered: int) -> None:
        self.session = session
        self.n_unanswered = n_unanswered

    @override
    async def __call__(self) -> "GuessingGameState | None":
        embed = discord.Embed(
            color=discord.Color.red(),
            title="Game ended",
            description=f"{self.n_unanswered} question{'' if self.n_unanswered == 1 else 's'} in a row went unanswered.",
        )
        embed.set_footer(text="Use `c>guess lb` to view the server leaderboard.")
        embed.add_field(name="Final Scores", value=self.session.print_score_list())

        await self.session.channel.send(embed=embed)

        return None


class EndGameReachedQuestionLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        embed = discord.Embed(
            color=discord.Color.green(),
            title="Game ended",
            description="The question limit has been reached.",
        )
        embed.set_footer(text="Use `c>guess lb` to view the server leaderboard.")
        embed.add_field(name="Final Scores", value=self.session.print_score_list())

        await self.session.channel.send(embed=embed)

        return None


class EndGameReachedScoreLimit(GuessingGameState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

    @override
    async def __call__(self) -> "GuessingGameState | None":
        embed = discord.Embed(
            color=discord.Color.green(),
            title="Game ended",
            description="The score limit has been reached.",
        )
        embed.set_footer(text="Use `c>guess lb` to view the server leaderboard.")
        embed.add_field(name="Final Scores", value=self.session.print_score_list())

        await self.session.channel.send(embed=embed)

        return None


class ShowAnswerState(GuessingGameState):
    def __init__(
        self,
        session: GuessingGameSession,
        song: Song,
        aliases: list[str],
        answer_image: io.BytesIO,
        accepted_answer: discord.Message | None,
        *,
        timed_out: bool = False,
        skipped: bool = False,
    ) -> None:
        self.session = session
        self.song = song
        self.aliases = aliases
        self.answer_image = answer_image
        self.accepted_answer = accepted_answer
        self.timed_out = timed_out
        self.skipped = skipped

    @override
    async def __call__(self) -> "GuessingGameState | None":
        if self.accepted_answer is not None:
            accepted_user = self.accepted_answer.author

            await self.accepted_answer.add_reaction("✅")
            await self.session.increment_score(accepted_user.id)

            if accepted_user.id not in self.session.scores:
                self.session.scores[accepted_user.id] = 1
            else:
                self.session.scores[accepted_user.id] += 1

            accuracy = max(
                [
                    fuzz.QRatio(
                        self.accepted_answer.content, alias, processor=str.lower
                    )
                    for alias in self.aliases
                ]
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

        embed = discord.Embed(
            color=color,
            description=(
                f"**Answer**: {'\n'.join([escape_markdown(x) for x in self.aliases])}\n"
                "\n"
                f"**Artist**: {escape_markdown(self.song.artist)}\n"
                f"**Category**: {escape_markdown(self.song.genre)}"
            ),
        )
        embed.set_image(url="attachment://image.png")

        if self.session.check_score_limit_reached():
            next_state = EndGameReachedScoreLimit(self.session)
        elif self.session.check_question_limit_reached():
            next_state = EndGameReachedQuestionLimit(self.session)
        elif self.session.questions_timed_out >= 3:
            next_state = EndGameTimedOut(self.session, 3)
        else:
            content += " Next question in 3 seconds..."
            next_state = WaitState(self.session, 3, AskQuestionState(self.session))

        await self.session.channel.send(
            content=content,
            embed=embed,
            file=discord.File(self.answer_image, "image.png"),
        )
        self.answer_image.close()

        return next_state


class AskQuestionState(GuessingGameSkippableState):
    def __init__(self, session: GuessingGameSession) -> None:
        self.session = session

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        song, aliases, answer_image, question_image = await self.session.get_question()

        question_embed = discord.Embed(
            title="Guess the song!",
            description=f"You have {self.session.time_per_question} seconds to guess the song.\nUse `{self.session.ctx.prefix}skip` to skip.",
            color=self.session.difficulty.color(),
        )
        question_embed.set_image(url="attachment://image.png")

        was_answered = False

        def check(m: discord.Message):
            nonlocal was_answered

            if not was_answered and m.channel == self.session.channel:
                was_answered = True

            return (
                m.channel == self.session.channel
                and max(
                    [
                        fuzz.QRatio(m.content, alias, processor=str.lower)
                        for alias in aliases
                    ]
                )
                >= 80
            )

        await self.session.channel.send(
            embed=question_embed,
            file=discord.File(question_image, "image.png"),
            mention_author=False,
        )
        question_image.close()

        try:
            self._task = asyncio.create_task(
                self.session.bot.wait_for(
                    "message", check=check, timeout=self.session.time_per_question
                )
            )
            msg = await self._task
            return ShowAnswerState(self.session, song, aliases, answer_image, msg)
        except CancelledError:
            return ShowAnswerState(
                self.session,
                song,
                aliases,
                answer_image,
                None,
                skipped=True,
            )
        except TimeoutError:
            if not was_answered:
                self.session.questions_timed_out += 1

            return ShowAnswerState(
                self.session,
                song,
                aliases,
                answer_image,
                None,
                timed_out=True,
            )
        finally:
            self.session.questions_done += 1

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()


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
            name="Difficulty", value=str(self.session.difficulty), inline=True
        )
        embed.add_field(
            name="Time to answer",
            value=str(self.session.time_per_question),
            inline=True,
        )

        if self.session.question_count is not None:
            embed.add_field(
                name="Questions", value=self.session.question_count, inline=True
            )

        if self.session.score_limit is not None:
            embed.add_field(
                name="Score limit", value=self.session.score_limit, inline=True
            )

        await self.session.ctx.send(embed=embed)
        return WaitState(self.session, 5, AskQuestionState(self.session))


async def run_state_machine(
    cog: "GamingCog",
    channel: "MessageableChannel",
    initial_state: GuessingGameState,
):
    current_state: GuessingGameState | None = initial_state

    while current_state is not None:
        with cog.state_for_game_session_lock:
            cog.state_for_game_session[channel.id] = current_state

        try:
            next_state = await current_state()

            if next_state is None:
                cog._clear_state(channel.id)
                break

            current_state = next_state
        except Exception as e:
            logger.exception("Error running guessing game state machine", exc_info=e)
            cog._clear_state(channel.id)

            embed = discord.Embed(
                color=discord.Color.red(),
                title="Game ended",
                description=(
                    "The game ended due to an error:\n"
                    "```python\n"
                    f"{''.join(traceback.format_exception_only(e))}\n"
                    "```\n"
                    "If this keeps happening, please ping the owner or contact them in the support Discord.",
                ),
            )
            await channel.send(embed=embed)
            break


class GamingCog(commands.Cog, name="Games"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

        self.game_sessions: dict[int, GuessingGameSession] = {}
        self.game_sessions_lock = Lock()

        self.state_for_game_session: dict[int, GuessingGameState] = {}
        self.state_for_game_session_lock = Lock()

    @commands.group("guess", invoke_without_command=True)
    async def guess(self, ctx: Context, *, arguments: str = ""):
        """Start a jacket art guessing game.

        **Parameters**
        `-d`, `--difficulty`: The difficulty of the game:
        - `BASIC` is the default mode, with 90x90 crop and no filters.
        - `ADVANCED` has a 75x75 crop and no filters.
        - `EXPERT` has a 75x75 crop and images may be rotated 90/180/270 degrees.
        - `MASTER` has a 60x60 crop and images may be rotated 90/180/270 degrees.
        - `ULTIMA` has a 60x60 crop, colors may be inverted, images may be rotated 90/180/270 degrees.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Default is 20 seconds.
        """

        if ctx.channel.id in self.game_sessions:
            await ctx.reply("There is already an ongoing session in this channel!")
            return

        def parse_difficulty(arg: str) -> Difficulty:
            if arg.upper().startswith("WORLD"):
                return Difficulty.WORLDS_END

            if arg.lower() == "we":
                return Difficulty.WORLDS_END

            return Difficulty.from_short_form(arg.upper()[:3])

        parser = DiscordArguments()
        parser.add_argument(
            "-d",
            "--difficulty",
            type=parse_difficulty,
            required=False,
            default=Difficulty.BASIC,
        )
        parser.add_argument("-q", "--questions", type=int, required=False, default=20)
        parser.add_argument("-s", "--score", type=int, required=False, default=None)
        parser.add_argument("-t", "--time", type=int, required=False, default=20)

        try:
            args, _ = await parser.parse_known_intermixed_args(shlex_split(arguments))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        difficulty: Difficulty = args.difficulty
        questions: int = args.questions
        score: int = args.score
        time: int = args.time

        if difficulty == Difficulty.WORLDS_END:
            msg = "WORLD'S END isn't supported yet. I don't think you're supposed to know what it has in store for you..."
            raise commands.BadArgument(msg)

        with self.game_sessions_lock:
            self.game_sessions[ctx.channel.id] = GuessingGameSession(
                ctx,
                difficulty=difficulty,
                question_count=questions,
                score_limit=score,
                time_per_question=time,
            )

        await run_state_machine(
            self, ctx.channel, StartState(self.game_sessions[ctx.channel.id])
        )

    @commands.hybrid_command("skip")
    async def skip(self, ctx: Context):
        if ctx.channel.id not in self.state_for_game_session:
            await ctx.reply("There is no ongoing sessions in this channel!")
            return

        state = self.state_for_game_session[ctx.channel.id]

        if isinstance(state, GuessingGameSkippableState):
            await state.skip()

        return

    @commands.guild_only()
    @guess.command("leaderboard", aliases=["lb"])
    async def guess_leaderboard(self, ctx: Context):
        assert ctx.guild is not None

        async with ctx.typing():
            view = GuessLeaderboardView(ctx)
            view.message = await ctx.reply(
                embeds=await view.format_page(),
                view=view,
                mention_author=False,
            )

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @guess.command("reset")
    async def guess_reset(self, ctx: Context):
        """Resets the c>guess leaderboard for this server.

        The user calling this command must have the Manage Server permission.
        """

        assert ctx.guild is not None

        async with self.bot.begin_db_session() as session:
            await session.execute(
                delete(GuessScore).where(GuessScore.guild_id == ctx.guild.id)
            )
            await session.commit()

        await ctx.message.add_reaction("✅")

    def _clear_state(self, channel_id: int):
        with self.state_for_game_session_lock:
            if channel_id in self.state_for_game_session:
                del self.state_for_game_session[channel_id]

        with self.game_sessions_lock:
            if channel_id in self.game_sessions:
                del self.game_sessions[channel_id]


async def setup(bot: "ChuniBot") -> None:
    cog = GamingCog(bot)
    await bot.add_cog(cog)
    # bot.add_view(NextGameButtonView(cog, cog.game_sessions))
