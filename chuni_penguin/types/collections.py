from dataclasses import dataclass

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class TitleRarity(Enum):
    normal = "normal"
    copper = "copper"
    silver = "silver"
    gold = "gold"
    platinum = "platina"
    rainbow = "rainbow"

    ongeki = "ongeki"
    staff = "staff"
    maimai = "maimai"

    phoenix_gold = "phoenix_g"
    phoenix_platinum = "phoenix_p"
    phoenix_rainbow = "phoenix_r"

    expert = "expert"
    master = "master"
    ultima = "ultima"

    version1 = "version1"
    version2 = "version2"
    version3 = "version3"

    kop = "kop"


@dataclass(slots=True, kw_only=True)
class UserAvatar:
    """The user's penguin avatar."""

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
    front: str


@dataclass(slots=True, kw_only=True)
class Title:
    content: str
    rarity: TitleRarity


@dataclass(slots=True, kw_only=True)
class PlayerCollections:
    avatar: UserAvatar
    titles: list[Title]
    nameplate: str
    map_icon: str
    system_voice: str
