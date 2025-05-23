from typing import Optional, override

from discord.components import SelectOption
from discord.ext.commands import Context
from discord.interactions import Interaction
from discord.ui import Select, View, select


class SelectToCompareView(View):
    def __init__(
        self,
        ctx: Context,
        options: list[tuple[str, int]],
        *,
        timeout: Optional[float] = 120,
        placeholder: str = "Select a score...",
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.value = None
        self.select.options = [SelectOption(label=k, value=str(v)) for k, v in options]
        self.select.placeholder = placeholder

    async def on_timeout(self) -> None:
        self.select.disabled = True
        self.clear_items()
        self.stop()

    @override
    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.user is not None and interaction.user.id in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
        }:
            return True

        await interaction.response.send_message(
            "This menu cannot be controlled by you, sorry!",
            ephemeral=True,
        )
        return False

    @select()
    async def select(self, interaction: Interaction, select: Select):
        await interaction.response.edit_message(content="Please wait...", view=None)
        self.value = select.values[0]
        self.stop()
