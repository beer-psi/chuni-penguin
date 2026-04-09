from dataclasses import dataclass
from datetime import datetime

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class LinkedGate(Enum):
    origin = 10001
    air = 10002
    star = 10003
    amazon = 10004
    crystal = 10005
    paradise = 10006
    new = 10007
    sun = 10008
    luminous = 10009
    verse = 10010

    def __str__(self) -> str:
        return f"Linked GATE {self.name.upper()}"


class LinkedGateStatus(Enum):
    not_found = 0
    under_analysis = 1
    linkable = 2
    clear = 3


class LinkLevel(Enum):
    i = 1
    ii = 2
    iii = 3
    iv = 4
    v = 5

    def __str__(self):
        return self.name.upper()


@dataclass(slots=True, kw_only=True)
class LinkedGateLeaderboardEntry:
    position: int
    player_name: str
    achieved_at: datetime
    link_level: LinkLevel


@dataclass(slots=True, kw_only=True)
class LinkedGateLeaderboard:
    title: str
    artist: str
    jacket_url: str
    cleared_at: datetime | None
    updated_at: datetime
    ranking: list[LinkedGateLeaderboardEntry]
