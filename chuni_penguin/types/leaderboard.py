from dataclasses import dataclass
from datetime import datetime

from .lamp import ClearLamp, ComboLamp
from .score import Judgements


@dataclass(slots=True, kw_only=True)
class LeaderboardEntry:
    position: int
    player_name: str
    score: int
    judgements: Judgements | None
    combo_lamp: ComboLamp | None
    clear_lamp: ClearLamp | None
    ajc_count: int | None
    achieved_at: datetime | None


@dataclass(slots=True, kw_only=True)
class Leaderboard:
    updated_at: datetime
    """The time the leaderboard was last updated."""

    ranking: list[LeaderboardEntry]
    """List of leaderboard entries, ordered from best to worst score."""
