# pyright: reportAttributeAccessIssue=false
import traceback
from typing import TYPE_CHECKING, Any, Generic, TypeVar, override

import discord

from chuni_penguin.config import config
from chuni_penguin.logging import logger

if TYPE_CHECKING:
    from chuni_penguin.context import PenguinContext

ContextT = TypeVar("ContextT", bound="PenguinContext", covariant=True)


class PenguinViewMixin(Generic[ContextT]):
    if TYPE_CHECKING:
        ctx: ContextT
        message: discord.Message | None

    async def _before_start(self, *, content: str | None = None) -> dict[str, Any]:
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

        # Same reason as above.
        self.message = message
        await message.edit(
            **kwargs,
            view=self,  # pyright: ignore[reportArgumentType]
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def start_in(
        self, messageable: discord.abc.Messageable, *, content: str | None = None
    ) -> discord.Message:
        kwargs = await self._before_start(content=content)

        # Same reason as above.
        self.message = await messageable.send(**kwargs, view=self)  # pyright: ignore[reportCallIssue, reportArgumentType]
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

    async def edit_message(self, interaction: discord.Interaction, **kwargs: Any):
        if interaction.response.is_done() and self.message is not None:
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
