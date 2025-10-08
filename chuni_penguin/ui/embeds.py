from collections.abc import Sequence
from typing import Any, override

import discord
from discord import Embed
from discord.ext.commands import Context

from ._pagination import ListPageSource, PaginationView


class EmbedPageSource(ListPageSource[discord.Embed]):
    def __init__(
        self,
        entries: list[discord.Embed],
        *,
        per_page: int,
        with_page_marker: bool = False,
    ) -> None:
        super().__init__(entries, per_page=per_page)
        self.with_page_marker = with_page_marker

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[discord.Embed]
    ) -> dict[str, Any]:
        embeds = [*page]

        if self.with_page_marker:
            embeds.append(
                discord.Embed(
                    description=f"Page {menu.current_page + 1}/{self.get_max_pages()}"
                )
            )

        return {"embeds": embeds}


class EmbedPaginationView(PaginationView):
    def __init__(self, ctx: Context, items: list[Embed], per_page: int = 1):
        super().__init__(ctx, EmbedPageSource(items, per_page=per_page))
