from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Protocol,
    TypeVar,
    override,
)

import discord.ui
from discord import Interaction
from discord.ext.commands import Context
from discord.utils import escape_markdown

from ._base import MessageKwargs, PenguinView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


PageT = TypeVar("PageT")
PageItemT = TypeVar("PageItemT")
FormatPageReturn = MessageKwargs | str | discord.Embed


class PageSourceProtocol(Protocol, Generic[PageT]):
    __slots__ = ("__prepared",)

    async def _prepare_once(self) -> Any:
        try:
            self.__prepared  # noqa: B018
        except AttributeError:
            await self.prepare()
            self.__prepared = True  # pyright: ignore[reportGeneralTypeIssues]

    async def prepare(self) -> Any:
        pass

    def is_paginating(self) -> bool: ...
    def get_max_pages(self) -> int | None: ...
    async def get_page(self, page_index: int) -> PageT: ...
    async def format_page(
        self, menu: "PaginationView", page: PageT
    ) -> FormatPageReturn: ...


class ListPageSource(PageSourceProtocol[Sequence[PageItemT]], Generic[PageItemT]):
    __slots__ = ("_max_pages", "entries", "per_page")

    def __init__(self, entries: Sequence[PageItemT], *, per_page: int) -> None:
        self.entries = entries
        self.per_page = per_page

        pages, left_over = divmod(len(entries), per_page)
        if left_over:
            pages += 1

        self._max_pages: int = pages

    @override
    def is_paginating(self) -> bool:
        return self._max_pages > 1

    @override
    def get_max_pages(self) -> int | None:
        return self._max_pages

    @override
    async def get_page(self, page_index: int) -> Sequence[PageItemT]:
        start = page_index * self.per_page
        end = start + self.per_page

        return self.entries[start:end]


class JumpToPageModal(discord.ui.Modal, title="Jump to page"):
    page = discord.ui.Label(
        text="Page",
        description="The page number to jump to.",
        component=discord.ui.TextInput(),
    )

    def __init__(self, view: "PaginationView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: Interaction["ChuniBot"], /) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        assert isinstance(self.page.component, discord.ui.TextInput)

        try:
            page_number = int(self.page.component.value)
        except ValueError:
            await interaction.response.send_message(
                f'Invalid page number: Cannot parse "{escape_markdown(self.page.component.value)}" as a number.',
                ephemeral=True,
            )
            return

        max_pages = self.view.source.get_max_pages()

        if page_number < 1 or (max_pages is not None and page_number > max_pages):
            if max_pages is None:
                message = "Invalid page number: Must be larger than 1."
            else:
                message = f"Invalid page number: Must be between 1 and {max_pages}."

            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.defer()

        if self.view.current_page != page_number - 1:
            await self.view.show_page(interaction, page_number - 1)


class PaginationView(PenguinView, Generic[PageT]):
    def __init__(
        self,
        ctx: Context,
        source: PageSourceProtocol[PageT],
        *,
        timeout: float | None = 180,
    ):
        super().__init__(ctx, timeout=timeout)

        self.source: PageSourceProtocol = source

        self._current_page: int = 0

        self.clear_items()
        self.fill_items()

    @property
    def current_page(self):
        return self._current_page

    @current_page.setter
    def current_page(self, value: int):
        self._current_page = value
        self._update_labels(self._current_page)

    def _update_labels(self, page_index: int):
        max_pages = self.source.get_max_pages()

        if max_pages is not None:
            self.jump_to_page.label = f"{page_index + 1}/{max_pages}"
        else:
            self.jump_to_page.label = f"{page_index + 1}"

        self.to_first_page.disabled = page_index == 0
        self.to_previous_page.disabled = page_index == 0
        self.to_next_page.disabled = (
            max_pages is not None and (page_index + 1) >= max_pages
        )
        self.to_last_page.disabled = max_pages is None or (page_index + 1) >= max_pages

    async def get_kwargs_from_page(self, page: PageT) -> MessageKwargs:
        value = await self.source.format_page(self, page)

        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            return {"content": value, "embed": None}

        if isinstance(value, discord.Embed):
            return {"content": None, "embed": value}

        return {}

    def fill_items(self):
        if not self.source.is_paginating():
            return

        max_pages = self.source.get_max_pages()
        use_last_and_first = max_pages is not None and max_pages > 2

        if use_last_and_first:
            self.add_item(self.to_first_page)

        self.add_item(self.to_previous_page)
        self.add_item(self.jump_to_page)
        self.add_item(self.to_next_page)

        if use_last_and_first:
            self.add_item(self.to_last_page)

    async def show_page(self, interaction: Interaction, page_index: int):
        page = await self.source.get_page(page_index)
        self.current_page = page_index
        kwargs = await self.get_kwargs_from_page(page)

        if not kwargs:
            return

        await self.edit_message(interaction, **kwargs)

    @override
    async def _before_start(self, *, content: str | None = None):
        await self.source._prepare_once()

        page = await self.source.get_page(self.current_page)
        kwargs = await self.get_kwargs_from_page(page)

        if content is not None:
            kwargs.setdefault("content", content)

        self._update_labels(self.current_page)

        return kwargs

    @discord.ui.button(label="<<", style=discord.ButtonStyle.grey, disabled=True)
    async def to_first_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.show_page(interaction, 0)

    @discord.ui.button(label="<", style=discord.ButtonStyle.grey, disabled=True)
    async def to_previous_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.show_page(interaction, max(self.current_page - 1, 0))

    @discord.ui.button(label="...", style=discord.ButtonStyle.grey)
    async def jump_to_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await interaction.response.send_modal(JumpToPageModal(self))

    @discord.ui.button(label=">", style=discord.ButtonStyle.grey)
    async def to_next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        max_pages = self.source.get_max_pages()

        if max_pages is not None:
            await self.show_page(interaction, min(self.current_page + 1, max_pages - 1))
        else:
            await self.show_page(interaction, self.current_page + 1)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.grey)
    async def to_last_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        max_pages = self.source.get_max_pages()

        # this should always happen since this button only shows up if there's a max page.
        if max_pages is not None:
            await self.show_page(interaction, max_pages - 1)
