import asyncio
import contextlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, Self, overload, override

import discord
import discord.context_managers
from discord.ext import commands
from discord.ext.commands.context import DeferTyping
from discord.ext.track_edits import EditTrackableContext
from discord.utils import MISSING, escape_markdown
from discord.webhook.async_ import WebhookMessage
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chuni_penguin.constants import SIMILARITY_THRESHOLD
from chuni_penguin.database import Alias, Chart, Song, UserConfig
from chuni_penguin.networks.types import Difficulty
from chuni_penguin.utils import did_you_mean_text

if TYPE_CHECKING:
    from .bot import ChuniBot
    from .cogs.botutils import SongSearchResult


def _typing_done_callback(fut: asyncio.Future) -> None:
    # just retrieve any exception and call it a day
    with contextlib.suppress(asyncio.CancelledError, Exception):
        fut.exception()


class Typing(discord.context_managers.Typing):
    async def wrapped_typer(self) -> None:
        with contextlib.suppress(discord.HTTPException):
            return await super().wrapped_typer()

    async def do_typing(self) -> None:
        channel = await self._get_channel()
        typing = channel._state.http.send_typing

        await typing(channel.id)

        while True:
            await asyncio.sleep(5)
            await typing(channel.id)

    async def __aenter__(self) -> None:
        self.task: asyncio.Task[None] = self.loop.create_task(self.do_typing())
        self.task.add_done_callback(_typing_done_callback)


class PenguinContext(EditTrackableContext["ChuniBot"]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.response: discord.Message | None = None
        self.user_config: UserConfig = MISSING

    @override
    async def reply(self, content: str | None = None, **kwargs: Any) -> discord.Message:
        # Ensure that if the original message was deleted somewhere in-between, we can still
        # safely put out the response

        try:
            msg = await super().reply(content, **kwargs)
        except discord.errors.HTTPException:
            msg = await self.send(content, **kwargs)

        self.response = msg

        return msg

    @classmethod
    async def from_interaction(
        cls, interaction: discord.Interaction["ChuniBot"], /
    ) -> Self:
        ctx = await super().from_interaction(interaction)
        ctx.user_config = await interaction.client.utils.fetch_user_config(
            interaction.user.id
        )

        return ctx

    @overload
    async def respond_or_edit(
        self,
        content: str | None = ...,
        *,
        files: Sequence[discord.File] = ...,
        suppress_embeds: bool = ...,
        delete_after: float | None = ...,
        allowed_mentions: discord.AllowedMentions = ...,
        view: discord.ui.LayoutView,
        ephemeral: bool = ...,
    ) -> discord.Message: ...

    @overload
    async def respond_or_edit(
        self,
        content: str | None = ...,
        *,
        embed: discord.Embed = ...,
        files: Sequence[discord.File] = ...,
        suppress_embeds: bool = ...,
        delete_after: float | None = ...,
        allowed_mentions: discord.AllowedMentions = ...,
        view: discord.ui.View | None = ...,
        ephemeral: bool = ...,
    ) -> discord.Message: ...

    @overload
    async def respond_or_edit(
        self,
        content: str | None = ...,
        *,
        embeds: Sequence[discord.Embed] = ...,
        files: Sequence[discord.File] = ...,
        suppress_embeds: bool = ...,
        delete_after: float | None = ...,
        allowed_mentions: discord.AllowedMentions = ...,
        view: discord.ui.View | None = ...,
        ephemeral: bool = ...,
    ) -> discord.Message: ...

    async def respond_or_edit(
        self, content: str | None = None, **kwargs: Any
    ) -> discord.Message:
        """Reply to the message referenced by this context, or update
        the response if we've replied before."""

        kwargs.pop("mention_author", None)

        if self.response is not None:
            edit_kwargs = {
                "content": content,
                "embed": kwargs.get("embed", MISSING),
                "embeds": kwargs.get("embeds", MISSING),
                "attachments": kwargs.get("files", MISSING),
                "view": kwargs.get("view", MISSING),
                "allowed_mentions": kwargs.get("allowed_mentions", MISSING),
            }

            if isinstance(self.response, discord.InteractionMessage):
                edit_kwargs["delete_after"] = kwargs.get("delete_after")
            elif not isinstance(self.response, WebhookMessage):
                edit_kwargs["suppress"] = kwargs.get("suppress_embeds", False)
                edit_kwargs["delete_after"] = kwargs.get("delete_after")

            with contextlib.suppress(discord.errors.NotFound):
                self.response = await self.response.edit(**edit_kwargs)

                return self.response

        return await self.reply(content=content, mention_author=False, **kwargs)

    @override
    def typing(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, *, ephemeral: bool = False
    ) -> Typing | DeferTyping["ChuniBot"]:
        if self.interaction is None:
            return Typing(self)

        return DeferTyping(self, ephemeral=ephemeral)

    async def resolve_message_reference(self) -> discord.Message | None:
        if (reference := self.message.reference) is not None:
            if isinstance(reference.resolved, discord.Message):
                return reference.resolved

            if reference.message_id is not None:
                try:
                    return await self.channel.fetch_message(reference.message_id)
                except discord.HTTPException:
                    msg = "Could not fetch the message that was replied to. Is it deleted?"
                    raise commands.CommandError(msg) from None
            else:
                msg = "The message reference did not point to a valid message."
                raise commands.BadArgument(msg)

        return None

    async def find_song(
        self,
        query: str,
        *,
        worlds_end: bool = False,
    ) -> tuple[Song, Alias | None, float] | tuple[None, None, Literal[0]]:
        from chuni_penguin.ui import ConfirmationYesView

        song, alias, similarity = await self.bot.utils.find_song(
            query,
            guild_id=self.guild.id if self.guild is not None else None,
            worlds_end=worlds_end,
        )

        if song is None:
            await self.reply(
                did_you_mean_text(self.clean_prefix, song, alias), mention_author=False
            )
            return (None, None, 0)

        if similarity < SIMILARITY_THRESHOLD:
            view = ConfirmationYesView(self)

            await view.start(content=did_you_mean_text(self.clean_prefix, song, alias))
            await view.wait()

            if not view.result:
                return (None, None, 0)

        return (song, alias, similarity)

    async def find_songs(
        self,
        query: str,
        *,
        available: bool | None = None,
        load_charts: bool = False,
        load_global_aliases: bool = False,
    ) -> "SongSearchResult | None":
        from chuni_penguin.ui import ConfirmationYesView

        result = await self.bot.utils.find_songs(
            query,
            guild_id=self.guild.id if self.guild is not None else None,
            available=available,
            load_charts=load_charts,
            load_global_aliases=load_global_aliases,
        )

        if result.similarity < SIMILARITY_THRESHOLD:
            view = ConfirmationYesView(self)

            await view.start(
                content=did_you_mean_text(
                    self.clean_prefix, result.songs[0], result.matched_alias
                )
            )
            await view.wait()

            if not view.result:
                return None

        return result

    async def find_chart(
        self,
        difficulty: Difficulty,
        query: str,
        select_prompt: str = "Select a chart:",
    ) -> Chart | None:
        """Finds a chart with the given difficulty and query, prompting the user if there are multiple
        options.

        Returns a 2-tuple, where the first item is the select message sent if the user was prompted, and
        the second item is the chart.
        """

        from chuni_penguin.ui import ConfirmationYesView, SelectToCompareView

        guild_id = self.guild.id if self.guild else None
        result = await self.bot.utils.find_songs(query, guild_id=guild_id)

        if result.similarity < SIMILARITY_THRESHOLD:
            view = ConfirmationYesView(self)
            msg = did_you_mean_text(self.prefix, result.songs[0], result.matched_alias)

            await view.start(content=msg)
            await view.wait()

            if not view.result:
                return None

        song_ids = {s.id for s in result.songs}

        async with self.bot.begin_db_session() as session:
            stmt = (
                select(Chart)
                .where(
                    (Chart.song_id.in_(song_ids))
                    & (Chart.difficulty == difficulty.short())
                )
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
            )
            charts = (await session.execute(stmt)).scalars().all()

        if len(charts) == 0:
            msg = f"No charts found for {escape_markdown(result.songs[0].title)} [{difficulty}]."
            raise commands.CommandError(msg)

        if len(charts) == 1:
            return charts[0]

        view = SelectToCompareView(
            self,
            [
                (
                    f"{x.song.title} [{Difficulty(x.difficulty)} {x.const or x.level}]",
                    i,
                )
                for i, x in enumerate(charts)
            ],
            placeholder="Select a chart...",
        )
        await self.respond_or_edit(select_prompt, view=view)

        await view.wait()

        if view.value is None:
            msg = "Timed out before selecting a chart."
            raise commands.CommandError(msg)

        return charts[int(view.value)]


class PenguinGuildContext(PenguinContext):
    """Utility context class used when we know that we're in a Discord guild; for instance,
    when using @commands.guild_only()."""

    author: discord.Member  # pyright: ignore[reportIncompatibleVariableOverride]
    guild: discord.Guild  # pyright: ignore[reportIncompatibleVariableOverride]
    channel: discord.VoiceChannel | discord.TextChannel | discord.Thread  # pyright: ignore[reportIncompatibleVariableOverride]
    me: discord.Member  # pyright: ignore[reportIncompatibleVariableOverride]
    prefix: str  # pyright: ignore[reportIncompatibleVariableOverride]
