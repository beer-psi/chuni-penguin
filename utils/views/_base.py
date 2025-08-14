import traceback
from typing import TYPE_CHECKING, Any, Generic, TypeVar, override

import discord

from utils.config import config
from utils.logging import logger

if TYPE_CHECKING:
    from utils.context import PenguinContext

ContextT = TypeVar("ContextT", bound="PenguinContext", covariant=True)


class PenguinView(discord.ui.View, Generic[ContextT]):
    """Common code for all views."""

    def __init__(self, ctx: ContextT, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)

        self.ctx: ContextT = ctx
        self.message: discord.Message | None = None

    async def _before_start(self, *, content: str | None = None) -> dict[str, Any]:
        return {"content": content}

    async def start(self, *, content: str | None = None, ephemeral: bool = False):
        kwargs = await self._before_start(content=content)

        self.message = await self.ctx.respond_or_edit(
            **kwargs, view=self, ephemeral=ephemeral
        )
        return self.message

    async def start_from(self, message: discord.Message, *, content: str | None = None):
        kwargs = await self._before_start(content=content)

        self.message = message
        await message.edit(**kwargs, view=self)

    async def start_in(
        self, messageable: discord.abc.Messageable, *, content: str | None = None
    ):
        kwargs = await self._before_start(content=content)

        self.message = await messageable.send(**kwargs, view=self)
        return self.message

    @override
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

    @override
    async def on_timeout(self) -> None:
        for item in self.children:
            if (
                not isinstance(item, discord.ui.Button)
                or item.style != discord.ButtonStyle.link
            ):
                self.remove_item(item)

        if self.message is not None:
            await self.message.edit(view=self)

        self.stop()

    @override
    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
        /,
    ) -> None:
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
