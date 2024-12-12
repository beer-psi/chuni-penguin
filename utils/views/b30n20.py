from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

import discord
from discord.ext.commands import Context

from chunithm_net.consts import KEY_PLAY_RATING
from utils import floor_to_ndp
from utils.components.score_card_embed import ScoreCardEmbed

from ._pagination import PaginationView

if TYPE_CHECKING:
    from chunithm_net.models.record import Record


class B30N20View(PaginationView):
    def __init__(self, ctx: Context, b30: Sequence["Record"], n20: Sequence["Record"]):
        super().__init__(ctx, n20, per_page=3)

        self.best30 = b30
        self.new20 = n20

        self.best30_total: Decimal = sum(
            (item.extras[KEY_PLAY_RATING] for item in b30), Decimal(0)
        )
        self.new20_total: Decimal = sum(
            (item.extras[KEY_PLAY_RATING] for item in n20), Decimal(0)
        )

        if len(b30) > 0:
            self.best30_average: Decimal = floor_to_ndp(self.best30_total / len(b30), 4)
        else:
            self.best30_average = Decimal(0)

        if len(n20) > 0:
            self.new20_average: Decimal = floor_to_ndp(self.new20_total / len(n20), 4)
        else:
            self.new20_average = Decimal(0)

        self.rating = floor_to_ndp((self.best30_total + self.new20_total) / 50, 2)

    @discord.ui.button(label="Best 30", style=discord.ButtonStyle.grey)
    async def toggle_rating_views(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if button.label == "Best 30":
            self.items = self.best30
            self.page = 0
            button.label = "New 20"
        elif button.label == "New 20":
            self.items = self.new20
            self.page = 0
            button.label = "Best 30"
        else:
            msg = f"Unknown button label: {button.label}"
            raise ValueError(msg)

        await self.callback(interaction)

    def format_content(self):
        return (
            f"**Best 30 average**: {self.best30_average}\n"
            f"**New 20 average**: {self.new20_average}\n"
            f"**Rating**: {self.rating}"
        )

    def format_page(self, items: Sequence["Record"], start_index: int = 0):
        embeds: list[discord.Embed] = [
            ScoreCardEmbed(item, index=start_index + idx + 1, show_lamps=False)
            for idx, item in enumerate(items)
        ]
        embeds.append(
            discord.Embed(description=f"Page {self.page + 1}/{self.max_index + 1}")
        )
        return embeds

    async def callback(self, interaction: discord.Interaction):
        begin = self.page * self.per_page
        end = (self.page + 1) * self.per_page
        await interaction.response.edit_message(
            embeds=self.format_page(self.items[begin:end], begin),
            view=self,
        )
