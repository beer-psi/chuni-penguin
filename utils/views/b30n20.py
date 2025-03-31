from decimal import Decimal
from typing import TYPE_CHECKING, override

import discord
from discord.ext.commands import Context

from chunithm_net.consts import KEY_PLAY_RATING
from utils import floor_to_ndp

from ._pagination import PaginationView
from .b30 import B30PageSource

if TYPE_CHECKING:
    from chunithm_net.models.record import Record


class B30N20View(PaginationView):
    def __init__(self, ctx: Context, b30: list["Record"], n20: list["Record"]):
        self.best30 = B30PageSource(
            records=b30, rating_slots=30, per_page=3, show_reachable=False
        )
        self.new20 = B30PageSource(
            records=n20, rating_slots=20, per_page=3, show_reachable=False
        )

        super().__init__(ctx, self.new20)
        self.add_item(self.toggle_rating_views)

        self.best30_total: int = sum((item.extras[KEY_PLAY_RATING] for item in b30), 0)
        self.new20_total: int = sum((item.extras[KEY_PLAY_RATING] for item in n20), 0)

    @override
    async def get_kwargs_from_page(self, page: list["Record"]):
        kwargs = await super().get_kwargs_from_page(page)
        kwargs["content"] = (
            f"**Best 30**: {self.best30_total}\n"
            f"**New 20**: {self.new20_total}\n"
            f"**Rating**: {self.best30_total + self.new20_total}"
        )

        return kwargs

    @discord.ui.button(label="Best 30", style=discord.ButtonStyle.grey)
    async def toggle_rating_views(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if button.label == "Best 30":
            self.source = self.best30
            button.label = "New 20"
        elif button.label == "New 20":
            self.source = self.new20
            button.label = "Best 30"
        else:
            msg = f"Unknown button label: {button.label}"
            raise ValueError(msg)

        await self.show_page(interaction, 0)
