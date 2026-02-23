import contextlib
import operator
import random
from collections import deque
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING, cast

import discord
import sqlalchemy
from discord.ext import commands, songbird
from sqlalchemy import ColumnElement, select

from chuni_penguin import flags
from chuni_penguin.constants import ASSETS_DIR, ChunithmVersion
from chuni_penguin.context import PenguinContext, PenguinGuildContext
from chuni_penguin.converters import (
    GenreConverter,
    Level,
    LevelRange,
    LevelRangeConverter,
    VersionConverter,
)
from chuni_penguin.database import Chart, Song
from chuni_penguin.logging import logged_prefix_command
from chuni_penguin.networks.types import Genre
from chuni_penguin.utils import AsyncRWLockMapping, get_jacket_url

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.gaming.cog import GamingCog


class RadioState:
    __slots__ = (
        "allowed_song_ids",
        "available_tracks",
        "genres",
        "levels",
        "stopped_by",
        "total_tracks",
        "versions",
        "volume",
    )

    def __init__(
        self,
        allowed_song_ids: set[int] | None = None,
        volume: int = 15,
    ):
        if volume < 0 or volume > 100:
            msg = "volume must be between 0 and 100"
            raise ValueError(msg)

        self.allowed_song_ids = allowed_song_ids
        self.stopped_by: discord.User | discord.Member | None = None
        self.volume = volume
        self.load_tracks()

    @property
    def remaining_tracks(self):
        return len(self.available_tracks)

    def load_tracks(self):
        self.available_tracks = deque(
            p
            for p in (ASSETS_DIR / "audio").iterdir()
            if p.is_file()
            and p.stem.isdigit()
            and (self.allowed_song_ids is None or int(p.stem) in self.allowed_song_ids)
        )
        self.total_tracks = len(self.available_tracks)
        random.shuffle(self.available_tracks)

    def next_track(self) -> Path | None:
        try:
            return self.available_tracks.popleft()
        except IndexError:
            self.load_tracks()
            return self.available_tracks.popleft()


class VoiceCog(commands.Cog, name="Voice"):
    def __init__(self, bot: "ChuniBot"):
        self.bot: "ChuniBot" = bot
        self.radio_states: AsyncRWLockMapping[int, RadioState] = AsyncRWLockMapping()

        games = bot.get_cog("Games")

        if games is None:
            msg = "This extension must be loaded after `chuni_penguin.cogs.gaming`."
            raise RuntimeError(msg)

        self.games: "GamingCog" = cast("GamingCog", games)

    @flags.command("radio")
    @flags.argument("-g", "--genres", type=GenreConverter, nargs="*")
    @flags.argument("-l", "--levels", type=LevelRangeConverter, nargs="*")
    @flags.argument("-v", "--versions", type=VersionConverter, nargs="*")
    @commands.guild_only()
    @logged_prefix_command
    async def radio(
        self,
        ctx: PenguinGuildContext,
        *,
        genres: list[Genre] | None = None,
        levels: list[Level | LevelRange] | None = None,
        versions: list[ChunithmVersion] | None = None,
    ):
        """Starts a radio of CHUNITHM songs.

        **Parameters**
        `-g`, `--genres`: Limit song pool to the provided genres.
        `-l`, `--levels`: Limit song pool to the provided chart levels.
        `-v`, `--versions`: Limit song pool to the provided versions.
        """

        if ctx.voice_client is not None:
            msg = "Another radio or voice guessing game is already ongoing in this server. Only one radio or voice guessing game can run at a time for each server."
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

        async with self.bot.begin_db_session() as session:
            query = select(Song.id).where(Song.id < 8000)

            if genres is not None:
                query = query.where(
                    Song.chunithm_catcode.in_([g.value for g in genres])
                )

            if levels is not None:
                level_conditions: list[ColumnElement[bool]] = []

                for level in levels:
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

                query = (
                    query.join(Chart, Song.id == Chart.song_id)
                    .group_by(Song.id)
                    .where(reduce(operator.or_, level_conditions))
                )

            if versions is not None:
                query = query.where(Song.version.in_(versions))

            song_ids = (await session.execute(query)).scalars().unique().all()
            state = RadioState(set(song_ids))

        if len(state.available_tracks) <= 0:
            msg = "There are no songs available for playing. Try widening your filters, if there are any."
            raise commands.CommandError(msg)

        async with self.radio_states.write() as radio_states:
            radio_states[voice_channel.id] = radio_states[ctx.channel.id] = state

        await voice_channel.connect(cls=songbird.SongbirdClient, self_deaf=True)
        await self.on_radio_play_next_track(ctx, state)

    @commands.hybrid_command("volume")
    @commands.guild_only()
    @commands.bot_has_permissions(add_reactions=True)
    @logged_prefix_command
    async def volume(
        self, ctx: PenguinGuildContext, volume: commands.Range[int, 1, 100]
    ):
        """Sets the volume of the current voice guessing game."""

        if not isinstance(ctx.voice_client, songbird.SongbirdClient):
            msg = "There are no active radios/voice guessing games in this server."
            raise commands.CommandError(msg)

        if (
            ctx.author.voice is None
            or ctx.author.voice.channel != ctx.voice_client.channel
        ):
            msg = "You are not in the current radio/voice guessing game."
            raise commands.CommandError(msg)

        has_channel = False

        async with self.games.game_sessions.read() as game_sessions:
            if ctx.channel.id in game_sessions:
                game_sessions[ctx.channel.id].volume = volume
                has_channel = True

        async with self.radio_states.read() as radio_states:
            if ctx.channel.id in radio_states:
                radio_states[ctx.channel.id].volume = volume
                has_channel = True

        if not has_channel:
            msg = "There are no ongoing radios/games in this channel."
            raise commands.CommandError(msg)

        ctx.voice_client.set_volume(volume / 100)

        if ctx.interaction is not None:
            await ctx.reply(f"Set volume to {volume}%", mention_author=False)
        else:
            await ctx.message.add_reaction("✅")

    @commands.hybrid_command("stop")
    @commands.bot_has_permissions(add_reactions=True)
    @logged_prefix_command
    async def stop(self, ctx: PenguinContext):
        """Stops the currently running radio or guessing game.."""

        channel_is_guessing_game = False
        channel_is_radio = False

        async with self.games.game_sessions.read() as game_sessions:
            if ctx.channel.id in game_sessions:
                session = game_sessions[ctx.channel.id]
                channel_is_guessing_game = True

                if (
                    ctx.author != session.ctx.author
                    and ctx.guild is not None
                    and not ctx.author.guild_permissions.manage_guild  # pyright: ignore[reportAttributeAccessIssue]
                ):
                    msg = "You cannot stop a game unless you started it or have the Manage Server permission."
                    raise commands.CommandError(msg)

        async with self.radio_states.read() as radio_states:
            if ctx.channel.id in radio_states:
                channel_is_radio = True

        if channel_is_guessing_game:
            async with self.games.game_sessions.read() as game_sessions:
                # The game may have already been stopped between reads.
                if ctx.channel.id not in game_sessions:
                    msg = "The game has already stopped."
                    raise commands.CommandError(msg)

                await game_sessions[ctx.channel.id].stop(ctx.author)
        elif channel_is_radio:
            async with self.radio_states.write() as radio_states:
                if ctx.channel.id not in radio_states:
                    msg = "The radio has already stopped."
                    raise commands.CommandError(msg)

                radio_states[ctx.channel.id].stopped_by = ctx.author
                del radio_states[ctx.channel.id]

                if isinstance(ctx.voice_client, songbird.SongbirdClient):
                    await ctx.voice_client.disconnect(force=False)
        else:
            msg = "There are no ongoing radios/games in this channel."
            raise commands.CommandError(msg)

        if ctx.interaction is not None:
            await ctx.reply("Stopped!", mention_author=False)
        else:
            await ctx.message.add_reaction("⏹")

    async def _clear_radio_state(self, channel_id: int):
        async with self.radio_states.write() as radio_states:
            with contextlib.suppress(IndexError):
                del radio_states[channel_id]

    @commands.Cog.listener()
    async def on_radio_play_next_track(
        self,
        ctx: PenguinGuildContext,
        state: RadioState,
    ):
        voice_client = ctx.voice_client

        if not isinstance(voice_client, songbird.SongbirdClient):
            await self._clear_radio_state(ctx.channel.id)
            return

        if state.stopped_by is not None:
            await self._clear_radio_state(ctx.channel.id)
            await voice_client.disconnect(force=False)
            return

        path = state.next_track()

        if path is None:
            await self._clear_radio_state(ctx.channel.id)
            await voice_client.disconnect(force=False)
            return

        async with ctx.bot.begin_db_session() as session:
            query = select(Song).where(Song.id == int(path.stem))
            song = (await session.execute(query)).scalar_one_or_none()

        if song is None:
            ctx.bot.dispatch("radio_play_next_track", ctx, state)
            return

        track = songbird.Track(songbird.File(str(path)))
        track.pause()

        try:
            track_handle = await voice_client.play(track)
        except discord.ClientException:
            await self._clear_radio_state(ctx.channel.id)
            await voice_client.disconnect(force=True)
            return

        track_handle.add_event(
            songbird.TrackEvent.End,
            lambda _: ctx.bot.dispatch("radio_play_next_track", ctx, state),
        )
        track_handle.set_volume(state.volume / 100)
        track_handle.play()

        displayed_version = song.version

        if song.release is not None:
            displayed_version += f" ({song.release})"

        await ctx.send(
            content=f"Now playing in {voice_client.channel.mention}",
            embed=discord.Embed(
                color=discord.Color.yellow(),
                title=song.title,
                description=(
                    f"**Artist**: {song.artist}\n"
                    f"**Category**: {song.genre}\n"
                    f"**Version**: {displayed_version}\n"
                ),
            )
            .set_thumbnail(url=get_jacket_url(song))
            .set_footer(
                text=f"Track {state.total_tracks - state.remaining_tracks} / {state.total_tracks}"
            ),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # Listen to voice channel disconnects to track voice channel ID changes
        if member != self.bot.user:
            return

        # To be disconnected, you must be in a voice channel first.
        if before.channel is None:
            return

        # We are disconnected if the after channel is None. The on_radio_play_next_track
        # loop will handle clearing states.
        if after.channel is None:
            await self._clear_radio_state(before.channel.id)
        else:
            async with self.radio_states.write() as radio_states:
                if before.channel.id not in radio_states:
                    return

                radio_states[after.channel.id] = radio_states[before.channel.id]

                del radio_states[before.channel.id]


async def setup(bot: "ChuniBot"):
    await bot.add_cog(VoiceCog(bot))
