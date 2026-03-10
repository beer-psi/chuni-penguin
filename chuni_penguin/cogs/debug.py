from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
import jishaku
import pyotp
from discord.ext import commands
from discord.utils import MISSING
from jishaku import OPTIONAL_FEATURES, STANDARD_FEATURES

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.ui._base import PenguinView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class DebugTOTPEntryModal(discord.ui.Modal, title="Enter TOTP"):
    totp = discord.ui.TextInput(label="TOTP")

    def __init__(
        self, view: "DebugTOTPEntryView", *, timeout: float | None = 180
    ) -> None:
        super().__init__(timeout=timeout)

        self.view = view
        self.interaction: discord.Interaction = MISSING

    async def on_submit(self, interaction: discord.Interaction["ChuniBot"], /) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        await interaction.response.defer(ephemeral=True)

        self.interaction = interaction
        self.view.stop()
        self.stop()


class DebugTOTPEntryView(PenguinView):
    def __init__(self, ctx: PenguinContext, *, timeout: float | None = 180) -> None:
        super().__init__(ctx, timeout=timeout)

        self.modal = DebugTOTPEntryModal(self, timeout=timeout)

    @discord.ui.button(label="Enter TOTP")
    async def enter_totp(
        self, interaction: discord.Interaction["ChuniBot"], _: discord.ui.Button
    ):
        await interaction.response.send_modal(self.modal)


class DebugCog(*OPTIONAL_FEATURES, *STANDARD_FEATURES):
    def __init__(self, bot: "ChuniBot") -> None:
        super().__init__(bot=bot)

        self._totp: pyotp.TOTP | None = (
            pyotp.TOTP(config.dangerous.debug_totp)
            if config.dangerous.debug_totp is not None
            else None
        )
        self._sudo_mode_until: datetime = datetime.fromtimestamp(0, tz=UTC)

    async def cog_check(self, ctx: PenguinContext):
        return await ctx.bot.is_owner(ctx.author)

    async def cog_before_invoke(self, ctx: PenguinContext):
        if config.dangerous.dev:  # Always allow jishaku commands in dev mode
            return

        if self._totp is None:
            msg = "Debugging commands are not enabled in production if 2FA is not enabled. Set a TOTP key in `dangerous.debug_totp` in the configuration file."
            raise commands.CommandError(msg)

        current_time = datetime.now(UTC)

        if current_time <= self._sudo_mode_until:
            self._sudo_mode_until = current_time + timedelta(minutes=15)
            return

        view = DebugTOTPEntryView(ctx)
        message = await view.start(
            content="Confirm access to debugging commands by entering a TOTP."
        )

        if await view.wait():
            msg = "Authentication timed out."
            raise commands.CommandError(msg)

        if not self._totp.verify(
            view.modal.totp.value, for_time=view.modal.interaction.created_at
        ):
            msg = "Invalid TOTP."
            raise commands.CommandError(msg)

        await message.delete()
        ctx.response = None

        self._sudo_mode_until = current_time + timedelta(minutes=15)


async def setup(bot: "ChuniBot"):
    jishaku.Flags.HIDE = True
    jishaku.Flags.ALWAYS_DM_TRACEBACK = True
    await bot.add_cog(DebugCog(bot))
