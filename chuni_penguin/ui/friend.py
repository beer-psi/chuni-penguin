from typing import TYPE_CHECKING, override

import discord
from discord.ext import commands
from discord.ext.commands.core import hooked_wrapped_callback
from discord.utils import MISSING, escape_markdown

from chuni_penguin.context import PenguinContext
from chuni_penguin.networks.types import Profile

from ._base import MessageKwargs, PenguinView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class FriendCodeEntryModal(discord.ui.Modal, title="Friend code"):
    friend_code = discord.ui.TextInput(label="Your friend code")
    remember_friend_code = discord.ui.Label(
        text="Remember friend code",
        component=discord.ui.Checkbox(default=True),
    )

    def __init__(
        self,
        ctx: PenguinContext,
        friend_code: str | None = None,
        *,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ) -> None:
        super().__init__(timeout=timeout, custom_id=custom_id)

        self.ctx = ctx
        self.friend_code.default = friend_code or ""

    # The client attached to the interaction is definitely ChuniBot.
    @override
    async def on_submit(self, interaction: discord.Interaction["ChuniBot"]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not self.friend_code.value:
            await interaction.response.send_message(
                content="A friend code was not provided.", ephemeral=True
            )
            return

        if not isinstance(self.remember_friend_code.component, discord.ui.Checkbox):
            await interaction.response.send_message(
                content="An internal error has occured.", ephemeral=True
            )
            return

        if self.remember_friend_code.component.value:
            await interaction.client.database.cookies.set_friend_code(
                interaction.user.id, self.friend_code.value
            )

        if self.ctx.command is None:
            await interaction.response.send_message(
                content="An internal error has occured.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            content="Please wait...", ephemeral=True
        )

        if self.ctx.interaction is not None and isinstance(
            self.ctx.command, discord.app_commands.Command
        ):
            kwargs = await self.ctx.command._transform_arguments(
                self.ctx.interaction, self.ctx.interaction.namespace
            )

            if "friend_code" in kwargs:
                kwargs["friend_code"] = self.friend_code.value
            else:
                kwargs["user"] = self.friend_code.value

            try:
                await self.ctx.command._do_call(self.ctx.interaction, kwargs)
            except discord.app_commands.AppCommandError as e:
                await interaction.client.tree.on_error(self.ctx.interaction, e)
        else:
            if "friend_code" in self.ctx.kwargs:
                self.ctx.kwargs["friend_code"] = self.friend_code.value
            else:
                self.ctx.kwargs["user"] = self.friend_code.value

            injected = hooked_wrapped_callback(
                self.ctx.command, self.ctx, self.ctx.command.callback
            )

            try:
                await injected(*self.ctx.args, **self.ctx.kwargs)
            except commands.CommandError as e:
                await self.ctx.command.dispatch_error(self.ctx, e)

        self.stop()

    @override
    async def on_timeout(self) -> None:
        await self.ctx.respond_or_edit(
            embed=discord.Embed(
                color=discord.Color.red(),
                title="Error",
                description=f"You are not logged in. Please send `{self.ctx.prefix}login` to log in.",
            )
        )


class FriendCodeOfferView(PenguinView[PenguinContext]):
    def __init__(
        self,
        ctx: PenguinContext,
        friend_code: str | None = None,
        *,
        timeout: float | None = 180,
    ) -> None:
        super().__init__(ctx, timeout=timeout)

        self.friend_code = friend_code

    async def _before_start(self, *, content: str | None = None) -> MessageKwargs:
        return {
            "content": content,
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                title="Not logged in",
                description="You are not logged in to the bot. It is possible to use a friend code for this command. Would you like to use a friend code?",
            ),
        }

    @override
    async def on_timeout(self) -> None:
        await self.ctx.respond_or_edit(
            embed=discord.Embed(
                color=discord.Color.red(),
                title="Error",
                description=f"You are not logged in. Please send `{self.ctx.prefix}login` to log in.",
            )
        )
        return await super().on_timeout()

    @discord.ui.button(style=discord.ButtonStyle.green, label="Use friend code")
    async def use_friend_code(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            FriendCodeEntryModal(self.ctx, self.friend_code)
        )
        self.stop()


class FriendRequestWaitView(PenguinView[PenguinContext]):
    def __init__(
        self,
        ctx: PenguinContext,
        bot_profile: Profile,
        *,
        timeout: float | None = 180,
    ) -> None:
        super().__init__(ctx, timeout=timeout)

        self.bot_profile = bot_profile

    async def _before_start(self, *, content: str | None = None) -> MessageKwargs:
        return {
            "content": content,
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                title="Friend request sent",
                description=f"Please accept the friend request from {escape_markdown(self.bot_profile.username)} to continue.",
            ),
        }

    @discord.ui.button(
        style=discord.ButtonStyle.green, label="I've accepted the friend request"
    )
    async def accepted_friend_request(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        await interaction.response.send_message(
            content="Please wait...", ephemeral=True
        )
        self.stop()
