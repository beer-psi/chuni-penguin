from collections.abc import Sequence
from typing import override

import discord
from discord import Embed
from discord.ext.commands import Context

from ._pagination import FormatPageReturn, ListPageSource, PaginationView


class EmbedPageSource(ListPageSource[discord.Embed]):
    def __init__(
        self,
        entries: list[discord.Embed],
        *,
        per_page: int,
    ) -> None:
        super().__init__(entries, per_page=per_page)

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[discord.Embed]
    ) -> FormatPageReturn:
        return {"embeds": page}


class EmbedPaginationView(PaginationView):
    def __init__(self, ctx: Context, items: list[Embed], per_page: int = 1):
        super().__init__(ctx, EmbedPageSource(items, per_page=per_page))
