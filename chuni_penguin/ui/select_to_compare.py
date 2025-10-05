from typing import TYPE_CHECKING, Optional

from discord.components import SelectOption
from discord.ext.commands import Context
from discord.interactions import Interaction
from discord.ui import Select, select

from ._base import PenguinView


class SelectToCompareView(PenguinView):
    def __init__(
        self,
        ctx: Context,
        options: list[tuple[str, int]],
        *,
        timeout: Optional[float] = 120,
        placeholder: str = "Select a score...",
    ):
        super().__init__(ctx, timeout=timeout)

        self.value = None
        self.select.options = [SelectOption(label=k, value=str(v)) for k, v in options]
        self.select.placeholder = placeholder

    if TYPE_CHECKING:
        select: Select
    else:

        @select()
        async def select(self, interaction: Interaction, select: Select):
            await interaction.response.edit_message(content="Please wait...", view=None)
            self.value = select.values[0]
            self.stop()
