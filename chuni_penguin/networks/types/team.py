from dataclasses import dataclass

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class TeamEmblem(Enum):
    normal = "normal"
    silver = "silver"
    gold = "gold"
    rainbow = "rainbow"
    purple = "purple"
    red = "red"
    yellow = "yellow"
    green = "green"


@dataclass(slots=True, kw_only=True)
class Team:
    emblem: TeamEmblem
    name: str
