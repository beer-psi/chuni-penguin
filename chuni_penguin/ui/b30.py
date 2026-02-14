from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, override

import discord
from discord.ext.commands import Context

from chuni_penguin.networks.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_PLAY_RATING,
)
from chuni_penguin.utils import floor_to_ndp

from ._pagination import FormatPageReturn, ListPageSource, PaginationView
from .components.score_card_embed import ScoreCardEmbed

if TYPE_CHECKING:
    from chuni_penguin.networks.types import Score


class B30PageSource(ListPageSource["Score"]):
    __slots__ = (
        "average",
        "has_estimated_play_rating",
        "reachable",
        "show_average",
        "show_lamps",
        "show_reachable",
        "synthesis_alt_jacket",
    )

    def __init__(
        self,
        *,
        records: Sequence["Score"],
        rating_slots: int = 30,
        per_page: int = 3,
        show_average: bool = True,
        show_reachable: bool = True,
        show_lamps: bool = False,
        synthesis_alt_jacket: str | None = None,
    ) -> None:
        super().__init__(records, per_page=per_page)

        total_rating = sum(
            (record.extras[KEY_PLAY_RATING] for record in records),
            start=Decimal(0),
        )
        max_play_rating = max(
            (record.extras[KEY_PLAY_RATING] for record in records), default=Decimal(0)
        )

        self.average = floor_to_ndp(total_rating / rating_slots, 4)
        self.reachable = floor_to_ndp(total_rating / 40 + max_play_rating / 4, 4)
        self.has_estimated_play_rating = any(
            record.extras.get(KEY_INTERNAL_LEVEL) is None for record in records
        )
        self.show_average = show_average
        self.show_reachable = show_reachable
        self.show_lamps = show_lamps
        self.synthesis_alt_jacket = synthesis_alt_jacket

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence["Score"]
    ) -> FormatPageReturn:
        start = menu.current_page * self.per_page
        embeds: list[discord.Embed] = [
            ScoreCardEmbed(
                record,
                show_lamps=self.show_lamps,
                index=start + i + 1,
                synthesis_alt_jacket=self.synthesis_alt_jacket,
            )
            for i, record in enumerate(page)
        ]

        kwargs: FormatPageReturn = {"embeds": embeds}

        if self.show_average or self.show_reachable or self.has_estimated_play_rating:
            kwargs["content"] = (
                (f"Average: **{self.average}**" if self.show_average else "")
                + (f"\nReachable: **{self.reachable}**" if self.show_reachable else "")
                + (
                    "\nPlay ratings marked with asterisks are estimated (due to lack of chart constants)."
                    if self.has_estimated_play_rating
                    else ""
                )
            )

        return kwargs


class B30View(PaginationView):
    def __init__(
        self,
        ctx: Context,
        items: Sequence["Score"],
        rating_slots: int = 30,
        per_page: int = 3,
        *,
        show_average: bool = True,
        show_reachable: bool = True,
        show_lamps: bool = False,
        synthesis_alt_jacket: str | None = None,
    ):
        super().__init__(
            ctx,
            B30PageSource(
                records=items,
                rating_slots=rating_slots,
                per_page=per_page,
                show_average=show_average,
                show_reachable=show_reachable,
                show_lamps=show_lamps,
                synthesis_alt_jacket=synthesis_alt_jacket,
            ),
        )
