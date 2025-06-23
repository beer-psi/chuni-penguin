import asyncio
import inspect
import traceback
from argparse import ArgumentError
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import discord
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import delete

from chunithm_net.models.enums import Difficulty
from database.models import GuessScore
from utils import shlex_split
from utils.argparse import DiscordArguments
from utils.converters import DifficultyConverter
from utils.logging import logged_prefix_command, logger
from utils.views.gaming import GuessLeaderboardView

from ._session import GuessingGameSession, GuessingGameType
from .states.base import GuessingGameSkippableState, GuessingGameState
from .states.start import StartState

if TYPE_CHECKING:
    from discord.abc import MessageableChannel

    from bot import ChuniBot
    from cogs.botutils import UtilsCog
    from cogs.events import EventsCog

ASSETS_DIR = Path(__file__).parent.parent / "assets"


async def run_state_machine(
    cog: "GamingCog",
    channel: "MessageableChannel",
    session: GuessingGameSession,
    initial_state: GuessingGameState,
):
    current_state: GuessingGameState | None = initial_state

    while current_state is not None:
        async with cog.state_for_game_session_lock:
            cog.state_for_game_session[channel.id] = current_state

        try:
            next_state = await current_state()

            if next_state is None:
                await cog._clear_state(channel.id)

                if session.voice_client is not None:
                    await session.voice_client.disconnect()

                break

            current_state = next_state
        except Exception as e:  # noqa: BLE001
            await logger.aexception(
                "Error running guessing game",
                tag="guessing_game_error",
                exc_info=e,
            )
            await cog._clear_state(channel.id)

            if session.voice_client is not None:
                await session.voice_client.disconnect()

            if events_cog := cast("EventsCog | None", cog.bot.get_cog("Events")):
                await events_cog._submit_error_to_webhook(session.ctx, e)

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
            await channel.send(embed=embed)
            break


@dataclass
class GuessArguments:
    difficulty: Difficulty
    questions: int
    score: int | None
    time: int
    wrong: int | None


class GamingCog(commands.Cog, name="Games"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

        self.game_tasks: dict[int, asyncio.Task] = {}
        self.game_tasks_lock = asyncio.Lock()

        self.game_sessions: dict[int, GuessingGameSession] = {}
        self.game_sessions_lock = asyncio.Lock()

        self.state_for_game_session: dict[int, GuessingGameState] = {}
        self.state_for_game_session_lock = asyncio.Lock()

    async def _parse_guess_arguments(self, ctx: Context, arguments: str):
        parser = DiscordArguments()
        parser.add_argument(
            "-d",
            "--difficulty",
            required=False,
            type=str,
            default="BASIC",
        )
        parser.add_argument("-q", "--questions", type=int, required=False, default=20)
        parser.add_argument("-s", "--score", type=int, required=False, default=None)
        parser.add_argument("-t", "--time", type=int, required=False, default=20)
        parser.add_argument("-w", "--wrong", type=int, required=False, default=None)

        try:
            args, _ = await parser.parse_known_intermixed_args(shlex_split(arguments))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        # HACK: I have no idea why this is a coroutine if the default value is used...
        if inspect.isawaitable(args.difficulty):
            args.difficulty = await args.difficulty

        difficulty: Difficulty = await DifficultyConverter().convert(
            ctx, args.difficulty
        )
        questions: int = args.questions
        score: int | None = args.score
        time: int = args.time
        wrong: int | None = args.wrong

        return GuessArguments(difficulty, questions, score, time, wrong)

    @commands.group("guess", invoke_without_command=True)
    @logged_prefix_command
    async def guess(self, ctx: Context):
        """Start a guessing game.

        **Parameters**
        `game_type`: The guessing game to play. Either `audio` or `jacket`.
        `-d`, `--difficulty`: The difficulty of the game. One of `BASIC`/`ADVANCED`/`EXPERT`/`MASTER`/`ULTIMA`. See help on specific guessing games for details.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Default is 20 seconds.
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        """

        await ctx.send_help(self.guess)

    @guess.command("jacket")
    @logged_prefix_command
    async def guess_jacket(self, ctx: Context, *, arguments: str = ""):
        """Starts a jacket art guessing game.

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
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        """

        await self._guess_without_voice_channel(ctx, GuessingGameType.IMAGE, arguments)

    @guess.command("audio")
    @logged_prefix_command
    async def guess_audio(self, ctx: Context, *, arguments: str = ""):
        """Starts an audio guessing game using voice messages.

        **Parameters**
        `-d`, `--difficulty`: The difficulty of the game:
        - `BASIC` is the default mode, with 15 seconds of the song played.
        - `ADVANCED` with 10 seconds of the song played.
        - `EXPERT` with 7 seconds of the song played.
        - `MASTER` with 4 seconds of the song played.
        - `ULTIMA` with 2 seconds of the song played.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Default is 20 seconds.
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        """

        await self._guess_without_voice_channel(
            ctx, GuessingGameType.VOICE_MESSAGE, arguments
        )

    @commands.guild_only()
    @guess.command("voice")
    @logged_prefix_command
    async def guess_voice(self, ctx: Context, *, arguments: str = ""):
        """Starts an audio guessing game in a voice call.

        **Parameters**
        `-d`, `--difficulty`: The difficulty of the game:
        - `BASIC` is the default mode, with 15 seconds of the song played.
        - `ADVANCED` with 10 seconds of the song played.
        - `EXPERT` with 7 seconds of the song played.
        - `MASTER` with 4 seconds of the song played.
        - `ULTIMA` with 2 seconds of the song played.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Default is 20 seconds.
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        """

        assert isinstance(ctx.author, discord.Member)

        if ctx.channel.id in self.game_sessions:
            msg = "There is already an ongoing session in this channel!"
            raise commands.CommandError(msg)

        if ctx.voice_client is not None:
            msg = "Another voice guessing game is already ongoing in this server. Only one voice guessing game can run at a time for each server."
            raise commands.CommandError(msg)

        if ctx.author.voice is None or ctx.author.voice.channel is None:
            msg = "You must connect to a voice channel to start this guessing game."
            raise commands.CommandError(msg)

        await ctx.author.voice.channel.connect(self_deaf=True)

        await self._guess_without_voice_channel(
            ctx, GuessingGameType.VOICE_CHANNEL, arguments
        )

    async def _guess_without_voice_channel(
        self, ctx: Context, game_type: GuessingGameType, arguments: str
    ):
        if ctx.channel.id in self.game_sessions:
            msg = "There is already an ongoing session in this channel!"
            raise commands.CommandError(msg)

        args = await self._parse_guess_arguments(ctx, arguments)

        if args.difficulty == Difficulty.WORLDS_END:
            msg = "WORLD'S END isn't supported yet. I don't think you're supposed to know what it has in store for you..."
            raise commands.BadArgument(msg)

        async with self.game_sessions_lock:
            session = self.game_sessions[ctx.channel.id] = GuessingGameSession(
                ctx,
                difficulty=args.difficulty,
                game_type=game_type,
                question_count=args.questions,
                score_limit=args.score,
                time_per_question=args.time,
                wrong_answers_limit=args.wrong,
            )

        async with self.game_tasks_lock:
            self.game_tasks[ctx.channel.id] = asyncio.create_task(
                run_state_machine(self, ctx.channel, session, StartState(session))
            )

    @commands.hybrid_command("skip")
    @logged_prefix_command
    async def skip(self, ctx: Context):
        """Skips a state of an ongoing guessing game.

        You can use this to skip a question, but also skip any waiting times,
        such as the starting 5-second wait.
        """
        async with self.game_sessions_lock:
            if ctx.channel.id not in self.game_sessions:
                msg = "There are no ongoing games in this channel."
                raise commands.CommandError(msg)

        async with self.state_for_game_session_lock:
            state = self.state_for_game_session[ctx.channel.id]

        if isinstance(state, GuessingGameSkippableState):
            await state.skip()

        return

    @commands.hybrid_command("stop")
    @logged_prefix_command
    async def stop(self, ctx: Context):
        """Stops the currently running guessing game."""

        async with self.game_sessions_lock:
            if ctx.channel.id not in self.game_sessions:
                msg = "There are no ongoing games in this channel."
                raise commands.CommandError(msg)

            session = self.game_sessions[ctx.channel.id]

        if (
            ctx.author != session.ctx.author
            and ctx.guild is not None
            and not ctx.author.guild_permissions.manage_guild  # pyright: ignore[reportAttributeAccessIssue]
        ):
            msg = "You cannot stop a game unless you started it or have the Manage Server permission."
            raise commands.CommandError(msg)

        async with self.state_for_game_session_lock:
            state = self.state_for_game_session[ctx.channel.id]

        session.stopped_by = ctx.author

        if isinstance(state, GuessingGameSkippableState):
            await state.skip()

        return

    @commands.guild_only()
    @guess.command("leaderboard", aliases=["lb"])
    @logged_prefix_command
    async def guess_leaderboard(self, ctx: Context):
        assert ctx.guild is not None

        async with ctx.typing():
            view = GuessLeaderboardView(ctx)
            await view.start()

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @guess.command("reset")
    @logged_prefix_command
    async def guess_reset(self, ctx: Context):
        """Resets the guess leaderboard for this server.

        The user calling this command must have the Manage Server permission.
        """

        assert ctx.guild is not None

        async with self.bot.begin_db_session() as session:
            await session.execute(
                delete(GuessScore).where(GuessScore.guild_id == ctx.guild.id)
            )
            await session.commit()

        await ctx.message.add_reaction("✅")

    async def _clear_state(self, channel_id: int):
        async with self.state_for_game_session_lock:
            if channel_id in self.state_for_game_session:
                del self.state_for_game_session[channel_id]

        async with self.game_sessions_lock:
            if channel_id in self.game_sessions:
                del self.game_sessions[channel_id]


async def setup(bot: "ChuniBot") -> None:
    cog = GamingCog(bot)
    await bot.add_cog(cog)
    # bot.add_view(NextGameButtonView(cog, cog.game_sessions))
