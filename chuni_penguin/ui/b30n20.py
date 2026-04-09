from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, override

import discord
from discord.ext.commands import Context

from chuni_penguin.utils import floor_to_ndp

from ._pagination import PaginationView
from .b30 import B30PageSource

if TYPE_CHECKING:
    from chuni_penguin.types import Score


class B30N20View(PaginationView):
    def __init__(
        self,
        ctx: Context,
        b30: Sequence["Score"],
        n20: Sequence["Score"],
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
        self.add_item(self.show_best30)
        self.add_item(self.show_new20)

        self.best30_total: Decimal = sum(
            (item.rating or Decimal(0) for item in b30), Decimal(0)
        )
        self.new20_total: Decimal = sum(
            (item.rating or Decimal(0) for item in n20), Decimal(0)
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

    async def _switch_rating_views(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
        source: B30PageSource,
    ):
        self.show_best30.style = discord.ButtonStyle.gray
        self.show_new20.style = discord.ButtonStyle.gray
        button.style = discord.ButtonStyle.green
        self.source = source

        await self.show_page(interaction, 0)

    @override
    async def get_kwargs_from_page(self, page: list["Score"]):
        kwargs = await super().get_kwargs_from_page(page)
        kwargs["content"] = (
            f"**Best 30 average**: {self.best30_average}\n"
            f"**New 20 average**: {self.new20_average}\n"
            f"**Rating**: {self.rating}"
        )

        return kwargs

    @discord.ui.button(label="Best 30", style=discord.ButtonStyle.grey)
    async def show_best30(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_rating_views(interaction, button, self.best30)

    @discord.ui.button(label="New 20", style=discord.ButtonStyle.green)
    async def show_new20(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._switch_rating_views(interaction, button, self.new20)
