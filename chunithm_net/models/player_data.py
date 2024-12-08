from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .enums import Possession, SkillClass


@dataclass
class Nameplate:
    content: str
    rarity: str


@dataclass
class Rating:
    current: float
    max: Optional[float] = None


@dataclass
class Currency:
    owned: int
    total: int


@dataclass
class Overpower:
    value: float
    progress: float


@dataclass(kw_only=True)
class UserAvatar:
    base: str
    back: str
    skinfoot_r: str
    skinfoot_l: str
    skin: str
    wear: str
    face: str
    face_cover: str
    head: str
    hand_r: str
    hand_l: str
    item_r: str
    item_l: str


@dataclass(kw_only=True)
class Team:
    # emblem: some_enum_here
    name: str


@dataclass(kw_only=True)
class PlayerData:
    possession: Possession = Possession.NONE

    character: Optional[str] = None
    character_frame: Optional[str] = None
    avatar: UserAvatar

    name: str

    reborn: int = 0
    lv: int

    playcount: Optional[int] = None
    last_play_date: datetime

    team: Optional[Team] = None
    overpower: Overpower
    nameplate: Nameplate
    rating: Rating
    currency: Optional[Currency] = None

    friend_code: Optional[str] = None

    emblem: Optional[SkillClass] = None
    medal: Optional[SkillClass] = None
