# pyright: reportAttributeAccessIssue=false
import contextlib
import traceback
from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    NotRequired,
    TypedDict,
    TypeVar,
    cast,
    override,
)

import discord

from chuni_penguin.config import config
from chuni_penguin.logging import logger

if TYPE_CHECKING:
    from chuni_penguin.cogs.events import EventsCog
    from chuni_penguin.context import PenguinContext

ContextT = TypeVar("ContextT", bound="PenguinContext", covariant=True)


class MessageKwargs(TypedDict):
    content: NotRequired[str | None]
    embed: NotRequired[discord.Embed | None]
    embeds: NotRequired[Sequence[discord.Embed]]
    files: NotRequired[Sequence[discord.File]]
    suppress_embeds: NotRequired[bool]
    delete_after: NotRequired[float | None]
    allowed_mentions: NotRequired[discord.AllowedMentions | None]
    view: NotRequired[discord.ui.View | discord.ui.LayoutView]


class PenguinViewMixin(Generic[ContextT]):
    if TYPE_CHECKING:
        ctx: ContextT
        message: discord.Message | None

    async def _before_start(self, *, content: str | None = None) -> MessageKwargs:
        return {"content": content}

    async def start(
        self, *, content: str | None = None, ephemeral: bool = False
    ) -> discord.Message:
        kwargs = await self._before_start(content=content)

        # This will either be a discord.ui.View or discord.ui.LayoutView
        # depending on what you inherited it from.
        self.message = await self.ctx.respond_or_edit(  # pyright: ignore[reportCallIssue]
            **kwargs,
            view=self,  # pyright: ignore[reportArgumentType]
            ephemeral=ephemeral,
        )
        return self.message  # pyright: ignore[reportReturnType]

    async def start_from(self, message: discord.Message, *, content: str | None = None):
        kwargs = await self._before_start(content=content)

        # Change some key names when unpacking kwargs into Message.edit
        if "suppress_embeds" in kwargs:
            kwargs["suppress"] = kwargs["suppress_embeds"]  # pyright: ignore[reportGeneralTypeIssues]
            del kwargs["suppress_embeds"]

        if "files" in kwargs:
            kwargs["attachments"] = kwargs["files"]  # pyright: ignore[reportGeneralTypeIssues]
            del kwargs["files"]

        # self will either be a discord.ui.View or discord.ui.LayoutView
        # depending on what you inherited it from.
        kwargs["view"] = self  # pyright: ignore[reportGeneralTypeIssues]
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()

        self.message = message

        # suppress_embeds kwarg has already been fixed above.
        await message.edit(**kwargs)  # pyright: ignore[reportCallIssue]

    async def start_in(
        self, messageable: discord.abc.Messageable, *, content: str | None = None
    ) -> discord.Message:
        kwargs = await self._before_start(content=content)

        # self will either be a discord.ui.View or discord.ui.LayoutView
        # depending on what you inherited it from.
        kwargs["view"] = self  # pyright: ignore[reportGeneralTypeIssues]

        # Same reason as above.
        self.message = await messageable.send(**kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]
        return self.message  # pyright: ignore[reportReturnType]

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id == self.ctx.author.id or await self.ctx.bot.is_owner(
            interaction.user
        ):
            return True

        await interaction.response.send_message(
            "This menu cannot be controlled by you, sorry!",
            ephemeral=True,
        )
        return False

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
        /,
    ) -> None:
        if isinstance(error, discord.NotFound):
            return

        events_cog = cast("EventsCog | None", interaction.client.get_cog("Events"))

        if events_cog is not None:
            embed, _ = await events_cog._construct_error_embed(interaction, None, error)  # pyright: ignore[reportArgumentType]

            if embed.description is not None:
                with contextlib.suppress(discord.NotFound):
                    if interaction.response.is_done():
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await interaction.response.send_message(
                            embed=embed, ephemeral=True
                        )

                return

        await logger.aexception(
            "Unhandled view error", tag="view_error", exc_info=error
        )

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Error",
            description=(
                "An unhandled error occurred. It dropped this message:\n"
                "```python\n"
                f"{''.join(traceback.format_exception_only(error))}\n"
                "```\n"
                "The error has been logged. Please try again later."
            ),
        )

        if config.bot.support_server_invite:
            assert embed.description is not None

            embed.description += "\n"
            embed.description += (
                f"If this error keeps happening, please join the [support server]({config.bot.support_server_invite}) "
                "and report the bug in the #help-bugs channel!"
            )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

        if events_cog is not None:
            await events_cog._submit_error_to_webhook(interaction, error)

    async def edit_message(self, interaction: discord.Interaction, **kwargs: Any):
        if interaction.response.is_done() and self.message is not None:
            if "suppress_embeds" in kwargs:
                kwargs["suppress"] = kwargs["suppress_embeds"]
                del kwargs["suppress_embeds"]

            await self.message.edit(
                **kwargs,
                view=self,  # pyright: ignore[reportArgumentType]
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        if not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs, view=self)  # pyright: ignore[reportArgumentType]
            return

        msg = "Interaction was responded to, and view does not have a message set."
        raise RuntimeError(msg)


class PenguinView(PenguinViewMixin[ContextT], discord.ui.View):
    """Common code for all views."""

    def __init__(self, ctx: ContextT, *, timeout: float | None = 180.0) -> None:
        discord.ui.View.__init__(self, timeout=timeout)

        self.ctx = ctx

    @override
    async def on_timeout(self) -> None:
        for item in self.children:
            if (
                not isinstance(item, discord.ui.Button)
                or item.style != discord.ButtonStyle.link
            ):
                self.remove_item(item)

        if self.message is not None:
            await self.message.edit(
                view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        self.stop()


class PenguinLayoutView(PenguinViewMixin[ContextT], discord.ui.LayoutView):
    """Common code for all layout views."""

    def __init__(self, ctx: ContextT, *, timeout: float | None = 180.0) -> None:
        discord.ui.LayoutView.__init__(self, timeout=timeout)

        self.ctx = ctx

    @override
    async def on_timeout(self) -> None:
        # Remove top-level buttons and selects entirely
        for item in self.children:
            if isinstance(item, discord.ui.ActionRow):
                self.remove_item(item)

        # I'd like to remove all the interactables inside the layout view too,
        # but that's really complex, since you have to e.g. unwrap TextDisplays
        # from a Section. That's a problem for another time. For now, just disable
        # them.
        for item in self.walk_children():
            if (
                isinstance(item, discord.ui.Button)
                and item.style != discord.ButtonStyle.link
            ) or isinstance(item, discord.ui.Select):
                item.disabled = True

        if self.message is not None:
            await self.message.edit(
                view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            )
