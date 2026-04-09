from dataclasses import dataclass
from decimal import Decimal

from discord.utils import MISSING

from chuni_penguin.calculation.overpower import calculate_overpower_max

try:
    from discord.enums import Enum, EnumMeta
except ImportError:
    from enum import Enum, EnumMeta


class DifficultyEnumMeta(EnumMeta):  # pyright: ignore[reportGeneralTypeIssues]
    def __call__(cls, value: str | int) -> "Difficulty":  # pyright: ignore[reportSelfClsParameterName]
        if isinstance(value, int):
            return super().__call__(value)

        upper = value.upper()

        if upper in ("BASIC", "BAS"):
            return cls.basic
        if upper in ("ADVANCED", "ADV"):
            return cls.advanced
        if upper in ("EXPERT", "EXP"):
            return cls.expert
        if upper in ("MASTER", "MAS"):
            return cls.master
        if upper in ("ULTIMA", "ULT"):
            return cls.ultima
        if upper in ("WORLD'S END", "WE"):
            return cls.worlds_end

        msg = f"{value!r} is not a valid {cls.__name__}"
        raise ValueError(msg)


class Difficulty(Enum, metaclass=DifficultyEnumMeta):
    basic = 0
    advanced = 1
    expert = 2
    master = 3
    ultima = 4
    worlds_end = 5

    def __str__(self):
        if self == Difficulty.worlds_end:
            return "WORLD'S END"

        return self.name.upper()

    def short(self) -> str:
        if self == Difficulty.worlds_end:
            return "WE"

        return self.name[:3].upper()

    def color(self):
        match self.value:
            case 0:
                return 0x009F7B
            case 1:
                return 0xF47900
            case 2:
                return 0xE92829
            case 3:
                return 0x8C1BE1
            case 4:
                return 0x131313
            case 5:
                return 0x0B6FF3

    @classmethod
    def from_embed_color(cls, color: int):
        if color == 0x009F7B:
            return cls.basic
        if color == 0xF47900:
            return cls.advanced
        if color == 0xE92829:
            return cls.expert
        if color == 0x8C1BE1:
            return cls.master
        if color == 0x131313:
            return cls.ultima
        if color == 0x0B6FF3:
            return cls.worlds_end

        msg = f"Unknown difficulty color: {color}"
        raise ValueError(msg)

    def emoji(self):
        match self.value:
            case 0:
                return ":green_square:"
            case 1:
                return ":yellow_square:"
            case 2:
                return ":red_square:"
            case 3:
                return ":purple_square:"
            case 4:
                return ":black_large_square:"
            case 5:
                return ":blue_square:"


class Genre(Enum):
    all = 99
    pops_and_anime = 0
    niconico = 2
    touhou_project = 3
    original = 5
    variety = 6
    irodorimidori = 7
    gekimai = 9

    def __str__(self) -> str:
        if self.value == 99:
            return "All genres"
        if self.value == 0:
            return "POPS & ANIME"
        if self.value == 2:
            return "niconico"
        if self.value == 3:
            return "東方Project"
        if self.value == 5:
            return "ORIGINAL"
        if self.value == 6:
            return "VARIETY"
        if self.value == 7:
            return "イロドリミドリ"
        if self.value == 9:
            return "ゲキマイ"

        msg = f"{self!r} is not a valid {self.__class__.__name__}"
        raise ValueError(msg)


@dataclass(slots=True, kw_only=True)
class Song:
    id: int
    title: str
    version: str | None = None
    genre: Genre | None = None
    jacket_url: str | None = None


@dataclass(slots=True, kw_only=True)
class Chart:
    difficulty: Difficulty
    level: str | None = None
    internal_level: float | None = None
    max_overpower: Decimal | None = MISSING
    max_combo: int | None = None

    def __post_init__(self):
        if self.max_overpower is MISSING:
            self.max_overpower = (
                calculate_overpower_max(self.internal_level)
                if self.internal_level is not None
                else None
            )
