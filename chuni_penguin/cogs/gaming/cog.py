import asyncio
import contextlib
from argparse import ArgumentError
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import MISSING
from sqlalchemy import delete

from chuni_penguin.context import PenguinContext, PenguinGuildContext
from chuni_penguin.converters import (
    DifficultyConverter,
    GenreConverter,
    Level,
    LevelRange,
    LevelRangeConverter,
)
from chuni_penguin.database import GuessScore
from chuni_penguin.flags import DiscordArguments
from chuni_penguin.logging import logged_prefix_command
from chuni_penguin.networks.types import Difficulty, Genre
from chuni_penguin.utils import AsyncRWLockMapping, shlex_split

from ._session import GuessingGameSession, GuessingGameType

if TYPE_CHECKING:
    from bot import ChuniBot


@dataclass(slots=True)
class GuessArguments:
    difficulty: Difficulty
    questions: int
    score: int | None
    time: int
    wrong: int | None
    hardcore: bool
    genres: list[Genre] | None
    volume: int
    levels: list[Level | LevelRange] | None
    seed: str | None


class GamingCog(commands.Cog, name="Games"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils

        self.game_tasks: set[asyncio.Task] = set()

        self.game_sessions: AsyncRWLockMapping[int, GuessingGameSession] = (
            AsyncRWLockMapping()
        )

        self.shutting_down = False

    async def _parse_guess_arguments(self, ctx: Context, arguments: str):
        parser = DiscordArguments()
        parser.add_argument(
            "-d",
            "--difficulty",
            required=False,
            type=lambda s: DifficultyConverter().convert(ctx, s),
            default=Difficulty.basic,
        )
        parser.add_argument("-q", "--questions", type=int, required=False, default=20)
        parser.add_argument("-s", "--score", type=int, required=False, default=None)
        parser.add_argument("-t", "--time", type=int, required=False, default=MISSING)
        parser.add_argument("-w", "--wrong", type=int, required=False, default=None)
        parser.add_argument("-h", "--hardcore", action="store_true")
        parser.add_argument("-g", "--genre", type=str, nargs="*")
        parser.add_argument("-v", "--volume", type=int, required=False, default=15)
        parser.add_argument(
            "-l",
            "--levels",
            type=lambda s: LevelRangeConverter().convert(ctx, s),
            nargs="*",
        )
        parser.add_argument("--seed", type=str, required=False, default=None)

        try:
            args, _ = await parser.parse_known_intermixed_args(shlex_split(arguments))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        difficulty: Difficulty = args.difficulty
        questions: int = args.questions
        score: int | None = args.score
        time: int = args.time
        wrong: int | None = args.wrong
        hardcore: bool = args.hardcore
        genre: list[str] | None = args.genre
        levels: list[Level | LevelRange] | None = args.levels
        volume: int = args.volume
        seed: str | None = args.seed

        if genre is not None and len(genre) == 0:
            msg = "No genres were specified."
            raise commands.BadArgument(msg)

        if levels is not None and len(levels) == 0:
            msg = "No levels were specified."
            raise commands.BadArgument(msg)

        if seed is not None and (
            len(seed) != 8
            or any(c not in "ABCDEFGHIJKLMNPQRSTUVWXYZ123456789" for c in seed)
        ):
            msg = "Invalid seed. Must contain exactly 8 uppercase characters (except `O`) and digits (except `0`)."
            raise commands.BadArgument(msg)

        if volume < 0 or volume > 100:
            msg = "Volume must be between 0 and 100."
            raise commands.BadArgument(msg)

        return GuessArguments(
            difficulty,
            questions,
            score,
            time,
            wrong,
            hardcore,
            await asyncio.gather(*[GenreConverter().convert(ctx, x) for x in genre])
            if genre is not None
            else None,
            volume,
            levels,
            seed,
        )

    @commands.group(
        "guess",
        usage="<game_type> [-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>] [-l <levels...>] [--seed <seed>]",
        invoke_without_command=True,
    )
    @logged_prefix_command
    async def guess(self, ctx: Context):
        """Start a guessing game. View help for each game mode for details."""

        await ctx.send_help(self.guess)

    @guess.command(
        "jacket",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>] [-l <levels...>] [--seed <seed>]",
    )
    @commands.bot_has_permissions(
        add_reactions=True,
        read_messages=True,
        attach_files=True,
    )
    @logged_prefix_command
    async def guess_jacket(self, ctx: PenguinContext, *, arguments: str = ""):
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
        `-h`, `--hardcore`: Hardcore mode, each player gets one chance to answer each question correctly.
        `-g`, `--genre`: Limit song pool to the provided genre. Can specify multiple genres, e.g. `-g original niconico`. **Games played with this option will not be counted towards the leaderboard!**
        `-l`, `--level`: Limit song pool to the provided chart levels. Can specify a level (13+), a chart constant (13.8), or a range (13.5-13.8). Can specify multiple levels, e.g. `-l 13+ 15`. **Games played with this option will not be counted towards the leaderboard!**
        `--seed`: Specify a seed for the game. A seed contains 8 uppercase characters and digits (except `O` and `0`). A seed only gives the same game if all other options are the same. A seed does not guarantee the same game as new songs get added. **Games played with this option will not be counted towards the leaderboard!**
        """

        await self._guess_common(ctx, GuessingGameType.IMAGE, arguments)

    @guess.command(
        "audio",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>] [-l <levels...>] [--seed <seed>]",
    )
    @commands.bot_has_permissions(
        add_reactions=True,
        read_messages=True,
        attach_files=True,
        send_voice_messages=True,
    )
    @logged_prefix_command
    async def guess_audio(self, ctx: PenguinContext, *, arguments: str = ""):
        """Starts an audio guessing game using voice messages.

        **Parameters**
        `-d`, `--difficulty`: The difficulty of the game:
        - `BASIC` is the default mode, with 15 seconds of the song played.
        - `ADVANCED` with 10 seconds of the song played.
        - `EXPERT` with 7 seconds of the song played.
        - `MASTER` with 4 seconds of the song played.
        - `ULTIMA` with 1 second of the song played.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Defaults to the audio length + 5 seconds
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        `-h`, `--hardcore`: Hardcore mode, each player gets one chance to answer each question correctly.
        `-g`, `--genre`: Limit song pool to the provided genre. Can specify multiple genres, e.g. `-g original niconico`. **Games played with this option will not be counted towards the leaderboard!**
        `-l`, `--level`: Limit song pool to the provided chart levels. Can specify a level (13+), a chart constant (13.8), or a range (13.5-13.8). Can specify multiple levels, e.g. `-l 13+ 15`. **Games played with this option will not be counted towards the leaderboard!**
        `--seed`: Specify a seed for the game. A seed contains 8 uppercase characters and digits (except `O` and `0`). A seed only gives the same game if all other options are the same. A seed does not guarantee the same game as new songs get added. **Games played with this option will not be counted towards the leaderboard!**
        """

        await self._guess_common(ctx, GuessingGameType.VOICE_MESSAGE, arguments)

    @guess.command(
        "voice",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-v <volume>] [-g <genres...>] [-l <levels...>] [--seed <seed>]",
    )
    @commands.guild_only()
    @commands.bot_has_permissions(
        add_reactions=True,
        read_messages=True,
        attach_files=True,
    )
    @logged_prefix_command
    async def guess_voice(self, ctx: PenguinGuildContext, *, arguments: str = ""):
        """Starts an audio guessing game in a voice call.

        **Parameters**
        `-d`, `--difficulty`: The difficulty of the game:
        - `BASIC` is the default mode, with 15 seconds of the song played.
        - `ADVANCED` with 10 seconds of the song played.
        - `EXPERT` with 7 seconds of the song played.
        - `MASTER` with 4 seconds of the song played.
        - `ULTIMA` with 1 second of the song played.
        `-q`, `--questions`: The number of questions for this game. Default is 20 questions.
        `-s`, `--score`: The score limit before this game is stopped. Default is no limit.
        `-t`, `--time`: The time (in seconds) for each question. Defaults to the audio length + 5 seconds.
        `-w`, `--wrong`: The number of questions to get wrong before the game is stopped. Default is unlimited.
        `-h`, `--hardcore`: Hardcore mode, each player gets one chance to answer each question correctly.
        `-g`, `--genre`: Limit song pool to the provided genre. Can specify multiple genres, e.g. `-g original niconico`. **Games played with this option will not be counted towards the leaderboard!**
        `-l`, `--level`: Limit song pool to the provided chart levels. Can specify a level (13+), a chart constant (13.8), or a range (13.5-13.8). Can specify multiple levels, e.g. `-l 13+ 15`. **Games played with this option will not be counted towards the leaderboard!**
        `-v`, `--volume`: The starting volume of the audio. Defaults to 15% (can be very loud!)
        `--seed`: Specify a seed for the game. A seed contains 8 uppercase characters and digits (except `O` and `0`). A seed only gives the same game if all other options are the same. A seed does not guarantee the same game as new songs get added. **Games played with this option will not be counted towards the leaderboard!**
        """

        session = await self._guess_common(
            ctx, GuessingGameType.VOICE_CHANNEL, arguments
        )

        assert ctx.voice_client is not None
        assert isinstance(
            ctx.voice_client.channel, discord.VoiceChannel | discord.StageChannel
        )

        async with self.game_sessions.write() as game_sessions:
            game_sessions[ctx.voice_client.channel.id] = session

    async def _guess_common(
        self,
        ctx: PenguinContext,
        game_type: GuessingGameType,
        arguments: str,
    ):
        if self.shutting_down:
            msg = "I am currently pending a restart. No new games can be started. Please wait a few minutes."
            raise commands.CommandError(msg)

        async with self.game_sessions.read() as game_sessions:
            if ctx.channel.id in game_sessions:
                msg = "There is already an ongoing session in this channel!"
                raise commands.CommandError(msg)

        args = await self._parse_guess_arguments(ctx, arguments)

        if args.difficulty == Difficulty.worlds_end:
            msg = "WORLD'S END isn't supported yet. I don't think you're supposed to know what it has in store for you..."
            raise commands.BadArgument(msg)

        async with self.game_sessions.write() as game_sessions:
            session = game_sessions[ctx.channel.id] = GuessingGameSession(
                ctx,
                difficulty=args.difficulty,
                game_type=game_type,
                question_count=args.questions,
                score_limit=args.score,
                time_per_question=args.time,
                wrong_answers_limit=args.wrong,
                hardcore_mode=args.hardcore,
                genres=args.genres,
                volume=args.volume,
                levels=args.levels,
                seed=args.seed,
            )

        if session.time_per_question is MISSING:
            if session.game_type == GuessingGameType.IMAGE:
                session.time_per_question = 20
            elif session.game_type in (
                GuessingGameType.VOICE_MESSAGE,
                GuessingGameType.VOICE_CHANNEL,
            ):
                session.time_per_question = session.get_audio_length() + 5

        if game_type == GuessingGameType.VOICE_CHANNEL and isinstance(
            ctx, PenguinGuildContext
        ):
            voice_client = await ctx.ensure_voice()
        else:
            voice_client = None

        async def after(_):
            await self._clear_state(ctx.channel.id)

            if voice_client is not None:
                await self._clear_state(voice_client.channel.id)

        game_task = asyncio.create_task(
            session.run(after=after), name=f"chuni-penguin-guess-{ctx.channel.id}"
        )

        self.game_tasks.add(game_task)
        game_task.add_done_callback(self.game_tasks.discard)

        return session

    @commands.hybrid_command("skip")
    @commands.bot_has_permissions(add_reactions=True)
    @logged_prefix_command
    async def skip(self, ctx: Context):
        """Skips a state of an ongoing guessing game.

        You can use this to skip a question, but also skip any waiting times,
        such as the starting 5-second wait.
        """
        async with self.game_sessions.read() as game_sessions:
            if ctx.channel.id not in game_sessions:
                msg = "There are no ongoing games in this channel."
                raise commands.CommandError(msg)

            await game_sessions[ctx.channel.id].skip()

        if ctx.interaction is not None:
            await ctx.reply("Skipped!", mention_author=False)
        else:
            await ctx.message.add_reaction("⏩")

    @commands.guild_only()
    @guess.command("leaderboard", aliases=["lb"])
    @logged_prefix_command
    async def guess_leaderboard(self, ctx: PenguinGuildContext):
        """View the score leaderboard for the current server."""

        from chuni_penguin.ui import GuessLeaderboardView

        async with ctx.typing():
            view = GuessLeaderboardView(ctx)
            await view.start()

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    @guess.command("reset")
    @logged_prefix_command
    async def guess_reset(self, ctx: PenguinGuildContext):
        """Resets the guess leaderboard for this server.

        The user invoking this command must have the Manage Server permission.
        """

        async with self.bot.begin_db_readwrite() as session:
            await session.execute(
                delete(GuessScore).where(GuessScore.guild_id == ctx.guild.id)
            )
            await session.commit()

        await ctx.message.add_reaction("✅")

    async def _clear_state(self, channel_id: int):
        async with self.game_sessions.write() as game_sessions:
            with contextlib.suppress(KeyError):
                del game_sessions[channel_id]

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member != self.bot.user or before.channel is None:
            return

        # Migrate the state to the new channel if we moved channels
        if after.channel is not None and after.channel != before.channel:
            async with self.game_sessions.write() as game_sessions:
                if before.channel.id not in game_sessions:
                    return

                session = game_sessions[before.channel.id]
                game_sessions[after.channel.id] = session

                # only stop tracking the previous channel if it's not the channel
                # where the questions/answers are sent
                if session.channel.id != before.channel.id:
                    del game_sessions[before.channel.id]
        else:
            async with self.game_sessions.read() as game_sessions:
                if before.channel.id not in game_sessions:
                    return

                await game_sessions[before.channel.id].skip()
