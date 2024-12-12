from abc import abstractmethod
from collections.abc import Sequence
from math import ceil

import discord.ui
from discord import Interaction
from discord.ext.commands import Context


class PaginationView(discord.ui.View):
    message: discord.Message

    def __init__(self, ctx: Context, items: Sequence, per_page: int = 5):
        super().__init__(timeout=120)
        self.ctx = ctx
        self._items = items
        self._page = 0
        self.per_page = per_page
        self.max_index = ceil(len(self._items) / per_page) - 1

        if self.max_index == 0:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    self.remove_item(item)
        elif self.max_index == 1:
            self.remove_item(self.to_last_page)
            self.remove_item(self.to_first_page)

    @property
    def page(self):
        return self._page

    @page.setter
    def page(self, value):
        self._page = max(0, min(value, self.max_index))
        self.toggle_buttons()

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, value):
        self._items = value
        self.max_index = ceil(len(self._items) / self.per_page) - 1

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user == self.ctx.author

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[reportGeneralTypeIssues]
        self.clear_items()
        await self.message.edit(view=self)

    def toggle_buttons(self):
        self.to_first_page.disabled = self.to_previous_page.disabled = self.page == 0
        self.to_next_page.disabled = self.to_last_page.disabled = (
            self.page == self.max_index
        )

    @abstractmethod
    async def callback(self, interaction: discord.Interaction): ...

    @discord.ui.button(label="<<", style=discord.ButtonStyle.grey, disabled=True)
    async def to_first_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        self.page = 0
        await self.callback(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.grey, disabled=True)
    async def to_previous_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        self.page -= 1
        await self.callback(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.grey)
    async def to_next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        self.page += 1
        await self.callback(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.grey)
    async def to_last_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        self.page = self.max_index
        await self.callback(interaction)
