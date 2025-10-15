try:
    from enum import Enum as StdlibEnum

    from discord.enums import Enum, EnumMeta
except ImportError:
    from enum import Enum, EnumMeta

    StdlibEnum = Enum


class Rarity(Enum):
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

    version1 = "version1"
    version2 = "version2"
    version3 = "version3"

    kop = "kop"


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


class ClearLamp(Enum):
    failed = 0
    clear = 1
    hard = 4
    brave = 5
    absolute = 6
    catastrophy = 7

    def __str__(self):
        return self.name.upper()

    def short(self) -> str:
        if self == ClearLamp.failed:
            return "FAILED"
        if self == ClearLamp.clear:
            return "CLR"
        if self == ClearLamp.hard:
            return "HRD"
        if self == ClearLamp.brave:
            return "BRV"
        if self == ClearLamp.absolute:
            return "ABS"
        if self == ClearLamp.catastrophy:
            return "CTS"

        msg = f"{self!r} is not a valid {self.__class__.__name__}"
        raise ValueError(msg)


class ComboLamp(Enum):
    none = 0
    full_combo = 1
    all_justice = 2
    all_justice_critical = 3

    def __str__(self):
        if self == ComboLamp.all_justice_critical:
            return "AJC"

        return self.name.upper().replace("_", " ")

    def short(self) -> str:
        if self == ComboLamp.all_justice_critical:
            return "AJC"
        if self == ComboLamp.all_justice:
            return "AJ"
        if self == ComboLamp.full_combo:
            return "FC"

        return "NONE"


class ChainLamp(Enum):
    none = 0
    # Yes, this is intentional, since full chain lamp was added after full chain+.
    full_chain = 2
    full_chain_plus = 1

    def __str__(self):
        if self == ChainLamp.full_chain_plus:
            return "FULL CHAIN+"

        return self.name.upper().replace("_", " ")

    def short(self) -> str:
        if self == ChainLamp.full_chain:
            return "FCH"
        if self == ChainLamp.full_chain_plus:
            return "FCH+"

        return "NONE"


class Rank(Enum):
    d = 0
    c = 1
    b = 2
    bb = 3
    bbb = 4
    a = 5
    aa = 6
    aaa = 7
    s = 8
    sp = 9
    ss = 10
    ssp = 11
    sss = 12
    sssp = 13

    def __str__(self):
        return self.name.replace("p", "+").upper()

    @classmethod
    def from_score(cls, score: int):
        if score >= 1_009_000:
            return cls.sssp
        if score >= 1_007_500:
            return cls.sss
        if score >= 1_005_000:
            return cls.ssp
        if score >= 1_000_000:
            return cls.ss
        if score >= 990_000:
            return cls.sp
        if score >= 975_000:
            return cls.s
        if score >= 950_000:
            return cls.aaa
        if score >= 925_000:
            return cls.aa
        if score >= 900_000:
            return cls.a
        if score >= 800_000:
            return cls.bbb
        if score >= 700_000:
            return cls.bb
        if score >= 600_000:
            return cls.b
        if score >= 500_000:
            return cls.c

        return cls.d

    @property
    def min_score(self):
        if self == Rank.d:
            return 0
        if self == Rank.c:
            return 500_000
        if self == Rank.b:
            return 600_000
        if self == Rank.bb:
            return 700_000
        if self == Rank.bbb:
            return 800_000
        if self == Rank.a:
            return 900_000
        if self == Rank.aa:
            return 925_000
        if self == Rank.aaa:
            return 950_000
        if self == Rank.s:
            return 975_000
        if self == Rank.sp:
            return 990_000
        if self == Rank.ss:
            return 1_000_000
        if self == Rank.ssp:
            return 1_005_000
        if self == Rank.sss:
            return 1_007_500
        if self == Rank.sssp:
            return 1_009_000

        msg = f"{self!r} is not a valid {self.__class__.__name__}"
        raise ValueError(msg)


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


class CourseClass(StdlibEnum):
    i = 1
    ii = 2
    iii = 3
    iv = 4
    v = 5
    infinite = 6
    extra = 7

    def __str__(self):
        if self == CourseClass.infinite:
            return "∞"

        return self.name.upper()


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
