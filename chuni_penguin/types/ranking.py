from dataclasses import dataclass
from datetime import datetime

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class RankingType(Enum):
    global_ = "global"
    friend = "friend"


class RankingDelta(Enum):
    down = 0
    keep = 1
    up = 2

    @property
    def emoji(self):
        if self == RankingDelta.down:
            return "\N{DOWNWARDS BLACK ARROW}"
        if self == RankingDelta.keep:
            return "\N{BLACK RIGHTWARDS ARROW}"
        if self == RankingDelta.up:
            return "\N{UPWARDS BLACK ARROW}"

        msg = f"Unknown enum variant {self!r}"
        raise ValueError(msg)


@dataclass(slots=True, kw_only=True)
class TeamRankingEntry:
    position: int
    team_name: str
    points: int
    delta: int
    ranking_delta: RankingDelta


@dataclass(slots=True, kw_only=True)
class TeamRanking:
    updated_at: datetime
    ranking: list[TeamRankingEntry]


@dataclass(slots=True, kw_only=True)
class RatingRankingEntry:
    position: int
    player_name: str
    rating: float


@dataclass(slots=True, kw_only=True)
class RatingRanking:
    updated_at: datetime
    ranking: list[RatingRankingEntry]


@dataclass(slots=True, kw_only=True)
class ScoreRankingEntry:
    position: int
    player_name: str
    score: int


@dataclass(slots=True, kw_only=True)
class ScoreRanking:
    updated_at: datetime
    ranking: list[ScoreRankingEntry]


@dataclass(slots=True, kw_only=True)
class CurrencyRankingEntry:
    position: int
    player_name: str
    currency: int


@dataclass(slots=True, kw_only=True)
class CurrencyRanking:
    updated_at: datetime
    ranking: list[CurrencyRankingEntry]
