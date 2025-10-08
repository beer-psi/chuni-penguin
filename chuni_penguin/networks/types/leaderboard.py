from dataclasses import dataclass
from datetime import datetime

from .score import Judgements


@dataclass(kw_only=True)
class LeaderboardEntry:
    position: int
    player_name: str
    score: int
    judgements: Judgements | None
    ajc_count: int | None
    achieved_at: datetime | None


@dataclass(kw_only=True)
class Leaderboard:
    updated_at: datetime
    """The time the leaderboard was last updated."""

    ranking: list[LeaderboardEntry]
    """List of leaderboard entries, ordered from best to worst score."""
