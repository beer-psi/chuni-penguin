from decimal import Decimal
from typing import TYPE_CHECKING, override

import discord
from discord.ext.commands import Context

from chuni_penguin.networks.chunithm_net import KEY_PLAY_RATING
from utils import floor_to_ndp

from ._pagination import PaginationView
from .b30 import B30PageSource

if TYPE_CHECKING:
    from chuni_penguin.networks.chunithm_net import Record


class B30N20View(PaginationView):
    def __init__(
        self,
        ctx: Context,
        b30: list["Record"],
        n20: list["Record"],
        *,
        synthesis_alt_jacket: str | None = None,
    ):
        self.best30 = B30PageSource(
            records=b30,
            rating_slots=30,
            per_page=3,
            show_reachable=False,
            synthesis_alt_jacket=synthesis_alt_jacket,
        )
        self.new20 = B30PageSource(
            records=n20,
            rating_slots=20,
            per_page=3,
            show_reachable=False,
            synthesis_alt_jacket=synthesis_alt_jacket,
        )

        super().__init__(ctx, self.new20)
        self.add_item(self.toggle_rating_views)

        self.best30_total: Decimal = sum(
            (item.extras[KEY_PLAY_RATING] for item in b30), Decimal(0)
        )
        self.new20_total: Decimal = sum(
            (item.extras[KEY_PLAY_RATING] for item in n20), Decimal(0)
        )

        if len(b30) > 0:
            self.best30_average: Decimal = floor_to_ndp(self.best30_total / 30, 4)
        else:
            self.best30_average = Decimal(0)

        if len(n20) > 0:
            self.new20_average: Decimal = floor_to_ndp(self.new20_total / 20, 4)
        else:
            self.new20_average = Decimal(0)

        self.rating = floor_to_ndp((self.best30_total + self.new20_total) / 50, 2)

    @override
    async def get_kwargs_from_page(self, page: list["Record"]):
        kwargs = await super().get_kwargs_from_page(page)
        kwargs["content"] = (
            f"**Best 30 average**: {self.best30_average}\n"
            f"**New 20 average**: {self.new20_average}\n"
            f"**Rating**: {self.rating}"
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

        self.clear_items()
        self.fill_items()
        self.add_item(self.toggle_rating_views)
        await self.show_page(interaction, 0)
