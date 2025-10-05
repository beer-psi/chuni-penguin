import discord
from discord.ext import commands

from chuni_penguin.views._base import PenguinView


class ConfirmationYesView(PenguinView):
    def __init__(self, ctx: commands.Context, *, timeout: float | None = 15):
        super().__init__(ctx, timeout=timeout)

        self.message: discord.Message | None = None
        self._result: bool = False

    @property
    def result(self):
        return self._result

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

        self._result = True

        if self.message is not None:
            await self.message.edit(view=None)

        self.stop()
