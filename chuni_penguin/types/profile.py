from dataclasses import dataclass, field
from datetime import datetime

from .collections import Title, UserAvatar
from .rating import RatingSystem
from .team import Team

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class Possession(Enum):
    none = "normal"
    silver = "silver"
    gold = "gold"
    platinum = "platina"
    rainbow = "rainbow"

    @property
    def color(self):
        match self.value:
            case "normal":
                return 0xCECECE
            case "silver":
                return 0x6BAAC7
            case "gold":
                return 0xFCE620
            case "platina":
                return 0xFFF6C5
            case "rainbow":
                return 0x0B6FF3


class SkillClass(Enum):
    i = 1
    ii = 2
    iii = 3
    iv = 4
    v = 5
    infinite = 6

    def __str__(self):
        if self == SkillClass.infinite:
            return "∞"

        return self.name.upper()


@dataclass(slots=True)
class Currency:
    owned: int
    total: int


@dataclass(slots=True, kw_only=True)
class OverPower:
    value: float
    """The user's raw overpower value."""

    percentage: float
    """
    The user's overpower value, expressed as a percentage of the
    maximum overpower value.
    """


@dataclass(slots=True, kw_only=True)
class Profile:
    username: str
    """The player's username."""

    url: str | None = None
    """
    A URL to visit the player's profile on the network's web UI, if it is publicly accessible.
    """

    titles: list[Title] = field(default_factory=list)
    """
    A list of the user's titles/trophies. Networks without titles can choose to return
    some other user-chosen text (e.g. statuses) if it is short enough.
    """

    team: Team | None = None

    profile_picture: str | None = None
    """
    A URL to the user's profile picture on the network.
    """

    profile_picture_frame: str | None = None
    """
    A URL to the user's profile picture frame on the network.
    """

    banner: str | None = None
    """
    A URL to the user's banner on the network.
    """

    medal: SkillClass | None = None
    """
    The user's medal, awarded when clearing one course of the class.
    """

    emblem: SkillClass | None = None
    """
    The user's emblem, awarded when clearing all courses of the class.
    """

    reincarnation_stars: int | None = None
    """
    The player's number of reincarnation stars. A reincarnation star is awarded every 100
    level, and then the player's level is reset to 1.
    """

    level: int | None = None
    """
    The player's current level, as a value between 1 and 99. Networks without this can
    safely use None.
    """

    rating_systems: list[RatingSystem] = field(default_factory=list)

    over_power: OverPower | None = None

    possession: Possession | None = None
    """
    The user's possession, achieved by reaching specific conditions. Note that a :const:`None`
    value is different from :attr:`Possession.none`: one is no possession data, and the other is
    the user not achieving possession on the network.
    """

    currency: Currency | None = None

    total_credits: int | None = None
    """The number of credits the user has played."""

    total_scores: int | None = None
    """The number of scores the user has on the network."""

    friend_code: str | None = None
    """
    The user's friend code on the network. This can be any string used
    to add/follow a player, e.g. a username.
    """

    extras: dict[str, str] = field(default_factory=dict)
    """
    A dictionary of extra key: value pairs to display on the profile. These wil be
    shown on Discord as-is without any processing.
    """

    last_played: datetime | None = None

    user_avatar: UserAvatar | None = None


@dataclass(slots=True, kw_only=True)
class Friend:
    profile: Profile
    friend_code: str
    is_favorite: bool | None = None
    is_rival: bool | None = None
