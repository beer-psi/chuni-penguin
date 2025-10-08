from dataclasses import dataclass

from .enums import Rarity


@dataclass(kw_only=True)
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


@dataclass(kw_only=True)
class Title:
    content: str
    rarity: Rarity


@dataclass(kw_only=True)
class PlayerCollections:
    avatar: UserAvatar
    titles: list[Title]
    nameplate: str
    map_icon: str
    system_voice: str
