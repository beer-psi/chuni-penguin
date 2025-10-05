import asyncio
import traceback
from argparse import ArgumentError
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands, songbird
from discord.ext.commands import Context, Range
from discord.utils import MISSING
from sqlalchemy import delete

from chuni_penguin.uiming import GuessLeaderboardView, RetryGameButton
from chunithm_net.models.enums import Difficulty, Genres
from database.models import GuessScore
from utils import shlex_split
from utils.context import PenguinGuildContext
from utils.converters import DifficultyConverter, GenreConverter
from utils.flags import DiscordArguments
from utils.logging import logged_prefix_command, logger

from ._session import GuessingGameSession, GuessingGameType
from .states.base import GuessingGameSkippableState, GuessingGameState
from .states.start import StartState

if TYPE_CHECKING:
    from discord.abc import MessageableChannel

    from bot import ChuniBot
    from cogs.events import EventsCog


@dataclass
class GuessArguments:
    difficulty: Difficulty
    questions: int
    score: int | None
    time: int
    wrong: int | None
    hardcore: bool
    genres: list[Genres] | None
    volume: int


class GamingCog(commands.Cog, name="Games"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils

        self.game_tasks: set[asyncio.Task] = set()

        self.game_sessions: dict[int, GuessingGameSession] = {}
        self.game_sessions_lock = asyncio.Lock()

        self.shutting_down = False

    async def _parse_guess_arguments(self, ctx: Context, arguments: str):
        parser = DiscordArguments()
        parser.add_argument(
            "-d",
            "--difficulty",
            required=False,
            type=lambda s: DifficultyConverter().convert(ctx, s),
            default=Difficulty.BASIC,
        )
        parser.add_argument("-q", "--questions", type=int, required=False, default=20)
        parser.add_argument("-s", "--score", type=int, required=False, default=None)
        parser.add_argument("-t", "--time", type=int, required=False, default=MISSING)
        parser.add_argument("-w", "--wrong", type=int, required=False, default=None)
        parser.add_argument("-h", "--hardcore", action="store_true")
        parser.add_argument("-g", "--genre", type=str, nargs="*")
        parser.add_argument("-v", "--volume", type=int, required=False, default=15)

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
        volume: int = args.volume

        if genre is not None and len(genre) == 0:
            msg = "No genres were specified."
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
        )

    @commands.group(
        "guess",
        usage="<game_type> [-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>]",
        invoke_without_command=True,
    )
    @logged_prefix_command
    async def guess(self, ctx: Context):
        """Start a guessing game. View help for each game mode for details."""

        await ctx.send_help(self.guess)

    @guess.command(
        "jacket",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>]",
    )
    @commands.bot_has_permissions(
        add_reactions=True,
        read_messages=True,
        attach_files=True,
    )
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
        `-h`, `--hardcore`: Hardcore mode, each player gets one chance to answer each question correctly.
        `-g`, `--genre`: Limit song pool to the provided genre. Can specify multiple genres, e.g. `-g original niconico`. **Games played with this option will not be counted towards the leaderboard!**
        """

        await self._guess_without_voice_channel(ctx, GuessingGameType.IMAGE, arguments)

    @guess.command(
        "audio",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-g <genres...>]",
    )
    @commands.bot_has_permissions(
        add_reactions=True,
        read_messages=True,
        attach_files=True,
    )
    @logged_prefix_command
    async def guess_audio(self, ctx: Context, *, arguments: str = ""):
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
        """

        await self._guess_without_voice_channel(
            ctx, GuessingGameType.VOICE_MESSAGE, arguments
        )

    @guess.command(
        "voice",
        usage="[-h] [-d <difficulty>] [-q <questions>] [-s <score>] [-t <time>] [-w <wrong>] [-v <volume>] [-g <genres...>]",
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
        `-v`, `--volume`: The starting volume of the audio. Defaults to 15% (can be very loud!)
        """

        if self.shutting_down:
            msg = "I am currently pending a restart. No new games can be started."
            raise commands.CommandError(msg)

        if ctx.channel.id in self.game_sessions:
            msg = "There is already an ongoing session in this channel!"
            raise commands.CommandError(msg)

        if ctx.voice_client is not None:
            msg = "Another voice guessing game is already ongoing in this server. Only one voice guessing game can run at a time for each server."
            raise commands.CommandError(msg)

        if (
            ctx.author.voice is None
            or (voice_channel := ctx.author.voice.channel) is None
        ):
            msg = "You must connect to a voice channel to start this guessing game."
            raise commands.CommandError(msg)

        voice_channel_permissions = voice_channel.permissions_for(ctx.me)
        missing = [
            p for p in ("connect", "speak") if not getattr(voice_channel_permissions, p)
        ]

        if missing:
            raise commands.BotMissingPermissions(missing)

        await voice_channel.connect(cls=songbird.SongbirdClient, self_deaf=True)

        self.game_sessions[voice_channel.id] = await self._guess_without_voice_channel(
            ctx, GuessingGameType.VOICE_CHANNEL, arguments
        )

    async def _guess_without_voice_channel(
        self, ctx: Context, game_type: GuessingGameType, arguments: str
    ):
        if self.shutting_down:
            msg = "I am currently pending a restart. No new games can be started. Please wait a few minutes."
            raise commands.CommandError(msg)

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
                hardcore_mode=args.hardcore,
                genres=args.genres,
                volume=args.volume,
            )

            if session.time_per_question is MISSING:
                if session.game_type == GuessingGameType.IMAGE:
                    session.time_per_question = 20
                elif session.game_type in (
                    GuessingGameType.VOICE_MESSAGE,
                    GuessingGameType.VOICE_CHANNEL,
                ):
                    session.time_per_question = session.get_audio_length() + 5

        voice_channel_id = (
            session.voice_client.channel.id
            if session.voice_client is not None
            else None
        )

        async def after(e):
            await self._clear_state(ctx.channel.id)

            if voice_channel_id is not None:
                await self._clear_state(voice_channel_id)

        game_task = asyncio.create_task(
            session.run(after=after), name=f"chuni-penguin-guess-{ctx.channel.id}"
        )

        self.game_tasks.add(game_task)
        game_task.add_done_callback(self.game_tasks.discard)

        return session

    @commands.hybrid_command("volume")
    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    @logged_prefix_command
    async def volume(self, ctx: Context, volume: Range[int, 1, 100]):
        """Sets the volume of the current voice guessing game."""

        assert isinstance(ctx.author, discord.Member)

        if ctx.voice_client is None:
            msg = "There are no active voice guessing games in this server."
            raise commands.CommandError(msg)

        if (
            ctx.author.voice is None
            or ctx.author.voice.channel != ctx.voice_client.channel
        ):
            msg = "You are not in the current voice guessing game."
            raise commands.CommandError(msg)

        async with self.game_sessions_lock:
            if ctx.channel.id not in self.game_sessions:
                msg = "There are no ongoing games in this channel."
                raise commands.CommandError(msg)

            self.game_sessions[ctx.channel.id].volume = volume

        cast(songbird.SongbirdClient, ctx.voice_client).set_volume(volume / 100)

        if ctx.interaction is not None:
            await ctx.reply(f"Set volume to {volume}%", mention_author=False)
        else:
            await ctx.message.add_reaction("✅")

    @commands.hybrid_command("skip")
    @commands.bot_has_permissions(add_reactions=True)
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

            await self.game_sessions[ctx.channel.id].skip()

        if ctx.interaction is not None:
            await ctx.reply("Skipped!", mention_author=False)
        else:
            await ctx.message.add_reaction("⏩")

    @commands.hybrid_command("stop")
    @commands.bot_has_permissions(add_reactions=True)
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

        async with self.game_sessions_lock:
            if ctx.channel.id not in self.game_sessions:
                msg = "The game has already stopped."
                raise commands.CommandError(msg)

            await self.game_sessions[ctx.channel.id].stop(ctx.author)

        if ctx.interaction is not None:
            await ctx.reply("Stopped!", mention_author=False)
        else:
            await ctx.message.add_reaction("⏹")

    @commands.guild_only()
    @guess.command("leaderboard", aliases=["lb"])
    @logged_prefix_command
    async def guess_leaderboard(self, ctx: PenguinGuildContext):
        """View the score leaderboard for the current server."""

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

        The user calling this command must have the Manage Server permission.
        """

        async with self.bot.begin_db_session() as session:
            await session.execute(
                delete(GuessScore).where(GuessScore.guild_id == ctx.guild.id)
            )
            await session.commit()

        await ctx.message.add_reaction("✅")

    async def _clear_state(self, channel_id: int):
        async with self.game_sessions_lock:
            if channel_id in self.game_sessions:
                del self.game_sessions[channel_id]

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # Listen to voice channel disconnects so we can stop voice games early.
        if member != self.bot.user:
            return

        # To be disconnected, you must be in a voice channel first.
        if before.channel is None:
            return

        # We are not disconnected if the after channel is not None.
        if after.channel is not None:
            return

        # We clear game states before disconnecting from the call, so this should be
        # safe if the game ended normally.
        async with self.game_sessions_lock:
            if before.channel.id not in self.game_sessions:
                return

            await self.game_sessions[before.channel.id].skip()


async def setup(bot: "ChuniBot") -> None:
    cog = GamingCog(bot)
    await bot.add_cog(cog)
    bot.add_dynamic_items(RetryGameButton)
