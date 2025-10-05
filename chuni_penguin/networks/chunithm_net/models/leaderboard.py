from dataclasses import dataclass
from datetime import datetime


@dataclass
class LeaderboardEntry:
    position: int
    player_name: str
    score: int
    ajc_count: int | None
    last_raised: datetime


@dataclass
class Leaderboard:
    updated_at: datetime
    ranking: list[LeaderboardEntry]
