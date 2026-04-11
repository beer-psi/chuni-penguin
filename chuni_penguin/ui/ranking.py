import unicodedata
from collections.abc import Sequence
from datetime import datetime
from math import ceil
from typing import TYPE_CHECKING, Protocol

import discord
from discord.ext.commands import Context

from chuni_penguin.types import Difficulty
from chuni_penguin.types.ranking import (
    CurrencyRanking,
    CurrencyRankingEntry,
    RankingType,
    RatingRanking,
    RatingRankingEntry,
    ScoreRanking,
    ScoreRankingEntry,
    TeamRanking,
    TeamRankingEntry,
)

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from ._pagination import FormatPageReturn


class TeamRankingPaginationSource(ListPageSource[TeamRankingEntry]):
    def __init__(
        self,
        network: str,
        network_color: discord.Color,
        ranking: TeamRanking,
        *,
        per_page: int = 10,
    ) -> None:
        super().__init__(ranking.ranking, per_page=per_page)

        self.network = network
        self.network_color = network_color
        self.ranking = ranking

    async def format_page(
        self, menu: "PaginationView", page: Sequence[TeamRankingEntry]
    ) -> "FormatPageReturn":
        embed = discord.Embed(
            color=self.network_color,
            title="Monthly Team Point Ranking",
            timestamp=self.ranking.updated_at,
        ).set_footer(text=self.network)

        try:
            max_position_length = max(len(str(entry.position)) for entry in page)
            max_team_name_length = max(len(entry.team_name) for entry in page)
        except ValueError:  # empty iterable:
            embed.description = "No teams found."
            return embed

        description_rows: list[str] = [
            f"`{entry.position: >{max_position_length}}` {entry.team_name:\u3000<{max_team_name_length}} ▸ {entry.points:,} ({'+' if entry.delta >= 0 else '-'}{entry.delta:,}) {entry.ranking_delta.emoji}"
            for entry in page
        ]
        embed.description = "\n".join(description_rows)

        return embed


class TeamRankingView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        network: str,
        network_color: discord.Color,
        ranking: TeamRanking,
        *,
        timeout: float | None = 180,
    ):
        super().__init__(
            ctx,
            TeamRankingPaginationSource(network, network_color, ranking),
            timeout=timeout,
        )


class RankingEntryProtocol(Protocol):
    position: int
    player_name: str


class RankingProtocol[T: RankingEntryProtocol](Protocol):
    updated_at: datetime
    ranking: list[T]


class NumericRankingPageSource[T: RankingEntryProtocol](ListPageSource[T]):
    def __init__(
        self,
        network: str,
        network_color: discord.Color,
        type: RankingType,
        ranking: RankingProtocol[T],
        *,
        per_page: int = 20,
    ):
        super().__init__(ranking.ranking, per_page=per_page)

        self.network = network
        self.network_color = network_color
        self.type = type
        self.ranking = ranking

    async def format_page(
        self, menu: "PaginationView", page: Sequence[T]
    ) -> "FormatPageReturn":
        embed = discord.Embed(
            color=self.network_color,
            title=self.get_title(),
            timestamp=self.ranking.updated_at,
        ).set_footer(text=self.network)

        if len(page) <= 0:
            embed.description = "No players found."
            return embed

        split_point = ceil(self.per_page / 2)
        left_half = page[:split_point]
        right_half = page[split_point:]
        left_half_max_position_length = max(
            len(str(entry.position)) for entry in left_half
        )
        left_half_max_name_length = max(len(entry.player_name) for entry in left_half)
        has_widechar = any(
            any(
                unicodedata.east_asian_width(c) in ("W", "F", "A")
                for c in record.player_name
            )
            for record in page
        )
        padding_char = "\u3000" if has_widechar else " "
        description_rows: list[str] = []

        try:
            right_half_max_position_length = max(
                len(str(entry.position)) for entry in right_half
            )
            right_half_max_name_length = max(
                len(entry.player_name) for entry in right_half
            )
        except ValueError:  # right half is empty, go down straight line
            description_rows = [
                f"`{left_entry.position: >{left_half_max_position_length}} {left_entry.player_name:{padding_char}<{left_half_max_name_length}} {self.get_entry_value(left_entry)}`"
                for left_entry in left_half
            ]
        else:
            for left_entry, right_entry in zip(left_half, right_half, strict=False):
                description_rows.append(
                    f"`{left_entry.position: >{left_half_max_position_length}} {left_entry.player_name:{padding_char}<{left_half_max_name_length}} {self.get_entry_value(left_entry)}`|"
                    f"`{right_entry.position: >{right_half_max_position_length}} {right_entry.player_name:{padding_char}<{right_half_max_name_length}} {self.get_entry_value(right_entry)}`"
                )

        embed.description = "\n".join(description_rows)

        return embed

    def get_title(self):
        return f"{self.type.value.title()} Ranking"

    def get_entry_value(self, entry: T):
        raise NotImplementedError


class RatingRankingPageSource(NumericRankingPageSource[RatingRankingEntry]):
    def get_title(self):
        return f"{self.type.value.title()} Ranking"

    def get_entry_value(self, entry: RatingRankingEntry):
        return f"{entry.rating:.2f}"


class RatingRankingView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        network: str,
        network_color: discord.Color,
        type: RankingType,
        ranking: RatingRanking,
        *,
        timeout: float | None = 180,
    ):
        super().__init__(
            ctx,
            RatingRankingPageSource(network, network_color, type, ranking),
            timeout=timeout,
        )


class CurrencyRankingPageSource(NumericRankingPageSource[CurrencyRankingEntry]):
    def get_title(self):
        return f"{self.type.value.title()} メモリー Ranking"

    def get_entry_value(self, entry: CurrencyRankingEntry):
        return f"{entry.currency:,}"


class CurrencyRankingView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        network: str,
        network_color: discord.Color,
        type: RankingType,
        ranking: CurrencyRanking,
        *,
        timeout: float | None = 180,
    ):
        super().__init__(
            ctx,
            CurrencyRankingPageSource(network, network_color, type, ranking),
            timeout=timeout,
        )


class ScoreRankingPageSource(ListPageSource[ScoreRankingEntry]):
    def __init__(
        self,
        network: str,
        network_color: discord.Color,
        type: RankingType,
        difficulty: Difficulty | None,
        ranking: ScoreRanking,
        *,
        per_page: int = 20,
    ):
        super().__init__(ranking.ranking, per_page=per_page)

        self.network = network
        self.network_color = network_color
        self.type = type
        self.difficulty = difficulty
        self.ranking = ranking

    async def format_page(
        self, menu: "PaginationView", page: Sequence[ScoreRankingEntry]
    ) -> "FormatPageReturn":
        embed = discord.Embed(
            color=(
                self.network_color
                if self.difficulty is None
                else self.difficulty.color()
            ),
            title=f"{self.type.value.title()} Score Ranking {'' if self.difficulty is None else f'({self.difficulty})'}",
            timestamp=self.ranking.updated_at,
        ).set_footer(text=self.network)

        if len(page) <= 0:
            embed.description = "No players found."
            return embed

        split_point = ceil(self.per_page / 2)
        left_half = page[:split_point]
        right_half = page[split_point:]
        left_half_max_position_length = max(
            len(str(entry.position)) for entry in left_half
        )
        left_half_max_name_length = max(len(entry.player_name) for entry in left_half)
        has_widechar = any(
            any(
                unicodedata.east_asian_width(c) in ("W", "F", "A")
                for c in record.player_name
            )
            for record in page
        )
        padding_char = "\u3000" if has_widechar else " "
        description_rows: list[str] = []

        try:
            right_half_max_position_length = max(
                len(str(entry.position)) for entry in right_half
            )
            right_half_max_name_length = max(
                len(entry.player_name) for entry in right_half
            )
        except ValueError:  # right half is empty, go down straight line
            description_rows = [
                f"`{left_entry.position: >{left_half_max_position_length}} {left_entry.player_name:{padding_char}<{left_half_max_name_length}} {left_entry.score:,}`"
                for left_entry in left_half
            ]
        else:
            for left_entry, right_entry in zip(left_half, right_half, strict=False):
                description_rows.append(
                    f"`{left_entry.position: >{left_half_max_position_length}} {left_entry.player_name:{padding_char}<{left_half_max_name_length}} {left_entry.score:,}`|"
                    f"`{right_entry.position: >{right_half_max_position_length}} {right_entry.player_name:{padding_char}<{right_half_max_name_length}} {right_entry.score:,}`"
                )

        embed.description = "\n".join(description_rows)

        return embed


class ScoreRankingView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        network: str,
        network_color: discord.Color,
        type: RankingType,
        difficulty: Difficulty | None,
        ranking: ScoreRanking,
        *,
        timeout: float | None = 180,
    ):
        super().__init__(
            ctx,
            ScoreRankingPageSource(network, network_color, type, difficulty, ranking),
            timeout=timeout,
        )
