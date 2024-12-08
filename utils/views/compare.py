from collections.abc import Sequence
from typing import TYPE_CHECKING

import discord
from discord.ext.commands import Context

from utils.components import ScoreCardEmbed

from ._pagination import PaginationView

if TYPE_CHECKING:
    from chunithm_net.models.record import Record


class CompareView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        items: Sequence["Record"],
        per_page: int = 1,
    ):
        super().__init__(ctx, items, per_page)

    async def callback(self, interaction: discord.Interaction):
        score = self.items[self.page]
        await interaction.response.edit_message(embed=ScoreCardEmbed(score), view=self)
