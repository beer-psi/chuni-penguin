from typing import Any, Generic, Protocol, TypeVar, override

import discord.ui
from discord import Interaction
from discord.ext.commands import Context

from chuni_penguin.views._base import PenguinView

PageT = TypeVar("PageT")
PageItemT = TypeVar("PageItemT")
FormatPageReturn = dict[str, Any] | str | discord.Embed


class PageSourceProtocol(Protocol, Generic[PageT]):
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
    async def get_page(self, page_number: int) -> PageT: ...
    async def format_page(
        self, menu: "PaginationView", page: PageT
    ) -> FormatPageReturn: ...


class ListPageSource(PageSourceProtocol[list[PageItemT]], Generic[PageItemT]):
    def __init__(self, entries: list[PageItemT], *, per_page: int) -> None:
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
    async def get_page(self, page_number: int) -> list[PageItemT]:
        start = page_number * self.per_page
        end = start + self.per_page

        return self.entries[start:end]


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

    def _update_labels(self, page_number: int):
        max_pages = self.source.get_max_pages()

        self.to_first_page.disabled = page_number == 0
        self.to_previous_page.disabled = page_number == 0
        self.to_next_page.disabled = (
            max_pages is not None and (page_number + 1) >= max_pages
        )
        self.to_last_page.disabled = max_pages is None or (page_number + 1) >= max_pages

    async def get_kwargs_from_page(self, page: PageT):
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
        self.add_item(self.to_next_page)

        if use_last_and_first:
            self.add_item(self.to_last_page)

    async def show_page(self, interaction: Interaction, page_number: int):
        page = await self.source.get_page(page_number)
        self.current_page = page_number
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
        await self.show_page(interaction, self.current_page - 1)

    @discord.ui.button(label=">", style=discord.ButtonStyle.grey)
    async def to_next_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.show_page(interaction, self.current_page + 1)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.grey)
    async def to_last_page(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        max_pages = self.source.get_max_pages()

        # this should always happen since this button only shows up if there's a max page.
        if max_pages is not None:
            await self.show_page(interaction, max_pages - 1)
