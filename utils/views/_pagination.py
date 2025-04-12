import traceback
from typing import Any, Generic, Protocol, TypeVar, override

import discord.ui
from discord import AllowedMentions, Interaction
from discord.ext.commands import Context

from utils.config import config
from utils.logging import logger

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


class PaginationView(discord.ui.View, Generic[PageT]):
    def __init__(
        self,
        ctx: Context,
        source: PageSourceProtocol[PageT],
        *,
        timeout: float | None = 180,
    ):
        super().__init__(timeout=timeout)

        self.ctx: Context = ctx
        self.source: PageSourceProtocol = source
        self.message: discord.Message | None = None

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

        if interaction.response.is_done():
            if self.message:
                await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def _before_start(self, *, content: str | None = None):
        await self.source._prepare_once()

        page = await self.source.get_page(self.current_page)
        kwargs = await self.get_kwargs_from_page(page)

        if content is not None:
            kwargs.setdefault("content", content)

        self._update_labels(self.current_page)

        return kwargs

    async def start(self, *, content: str | None = None, ephemeral: bool = False):
        kwargs = await self._before_start(content=content)

        self.message = await self.ctx.reply(
            **kwargs,
            view=self,
            ephemeral=ephemeral,
            mention_author=False,
        )
        return self.message

    async def start_from(self, message: discord.Message, *, content: str | None = None):
        kwargs = await self._before_start(content=content)

        self.message = message
        await message.edit(
            **kwargs,
            view=self,
            allowed_mentions=AllowedMentions.none(),
        )

    async def start_in(
        self, messageable: discord.abc.Messageable, *, content: str | None = None
    ):
        kwargs = await self._before_start(content=content)

        self.message = await messageable.send(**kwargs, view=self)
        return self.message

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

    @override
    async def on_timeout(self) -> None:
        for item in self.children:
            if (
                not isinstance(item, discord.ui.Button)
                or item.style != discord.ButtonStyle.link
            ):
                self.remove_item(item)

        if self.message is not None:
            await self.message.edit(view=self)

    @override
    async def on_error(
        self, interaction: Interaction, error: Exception, item: discord.ui.Item[Any], /
    ) -> None:
        await logger.aexception(
            "Unhandled view error", tag="view_error", exc_info=error
        )

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Error",
            description=(
                "An unhandled error occurred. It dropped this message:\n"
                "```python\n"
                f"{''.join(traceback.format_exception_only(error))}\n"
                "```\n"
                "The error has been logged. Please try again later."
            ),
        )

        if config.bot.support_server_invite:
            assert embed.description is not None

            embed.description += "\n"
            embed.description += (
                f"If this error keeps happening, please join the [support server]({config.bot.support_server_invite}) "
                "and report the bug in the #help-bugs channel!"
            )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

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


# class PaginationView(discord.ui.View):
#     message: discord.Message

#     def __init__(self, ctx: Context, items: Sequence, per_page: int = 5):
#         super().__init__(timeout=120)
#         self.ctx = ctx
#         self._items = items
#         self._page = 0
#         self.per_page = per_page
#         self.max_index = ceil(len(self._items) / per_page) - 1

#         if self.max_index == 0:
#             for item in self.children:
#                 if isinstance(item, discord.ui.Button):
#                     self.remove_item(item)
#         elif self.max_index == 1:
#             self.remove_item(self.to_last_page)
#             self.remove_item(self.to_first_page)

#     @property
#     def page(self):
#         return self._page

#     @page.setter
#     def page(self, value):
#         self._page = max(0, min(value, self.max_index))
#         self.toggle_buttons()

#     @property
#     def items(self):
#         return self._items

#     @items.setter
#     def items(self, value):
#         self._items = value
#         self.max_index = ceil(len(self._items) / self.per_page) - 1

#     async def interaction_check(self, interaction: Interaction) -> bool:
#         return interaction.user == self.ctx.author

#     async def on_timeout(self) -> None:
#         for item in self.children:
#             if hasattr(item, "disabled"):
#                 item.disabled = True  # type: ignore[reportGeneralTypeIssues]
#         self.clear_items()
#         await self.message.edit(view=self)

#     def toggle_buttons(self):
#         self.to_first_page.disabled = self.to_previous_page.disabled = self.page == 0
#         self.to_next_page.disabled = self.to_last_page.disabled = (
#             self.page == self.max_index
#         )

#     @abstractmethod
#     async def callback(self, interaction: discord.Interaction): ...

#     @discord.ui.button(label="<<", style=discord.ButtonStyle.grey, disabled=True)
#     async def to_first_page(
#         self, interaction: discord.Interaction, _: discord.ui.Button
#     ):
#         self.page = 0
#         await self.callback(interaction)

#     @discord.ui.button(label="<", style=discord.ButtonStyle.grey, disabled=True)
#     async def to_previous_page(
#         self, interaction: discord.Interaction, _: discord.ui.Button
#     ):
#         self.page -= 1
#         await self.callback(interaction)

#     @discord.ui.button(label=">", style=discord.ButtonStyle.grey)
#     async def to_next_page(
#         self, interaction: discord.Interaction, _: discord.ui.Button
#     ):
#         self.page += 1
#         await self.callback(interaction)

#     @discord.ui.button(label=">>", style=discord.ButtonStyle.grey)
#     async def to_last_page(
#         self, interaction: discord.Interaction, _: discord.ui.Button
#     ):
#         self.page = self.max_index
#         await self.callback(interaction)
