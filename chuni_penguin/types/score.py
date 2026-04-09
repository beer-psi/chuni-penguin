from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Self

from discord.utils import MISSING

from .lamp import ChainLamp, ClearLamp, ComboLamp
from .song import Chart, Song

try:
    from enum import Enum as StdlibEnum

    from discord.enums import Enum
except ImportError:
    from enum import Enum

    StdlibEnum = Enum


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


@dataclass(slots=True, kw_only=True)
class Judgements:
    justice_heaven: int | None = None
    justice_critical: int
    justice: int
    attack: int
    miss: int


@dataclass(slots=True, kw_only=True)
class NotePercentage:
    tap: float
    hold: float
    slide: float
    air: float
    flick: float


@dataclass(slots=True, kw_only=True)
class Skill:
    name: str
    grade: int | None


@dataclass(slots=True, kw_only=True)
class Score:
    song: Song
    chart: Chart

    score: int
    rank: Rank = MISSING
    clear_lamp: ClearLamp
    combo_lamp: ComboLamp
    chain_lamp: ChainLamp = ChainLamp.none

    max_combo: int | None = None
    judgements: Judgements | None = None
    note_percentage: NotePercentage | None = None

    achieved_at: datetime | None = None

    rating: Decimal | None = None
    ongeki_rating: Decimal | None = None
    ongeki_platinum_rating: Decimal | None = None
    overpower: Decimal | None = None

    # Adapter specific state (e.g. detailed recent identifier. should not be needed
    # otherwise)
    _memo: str | None = None

    def __post_init__(self):
        if self.rank is MISSING or self.rank == Rank.d:
            self.rank = Rank.from_score(self.score)


@dataclass(slots=True, kw_only=True)
class PersonalBest(Score):
    play_count: int | None = None
    ajc_count: int | None = None

    @classmethod
    def from_score(cls, score: Score) -> Self:
        return cls(
            song=score.song,
            chart=score.chart,
            score=score.score,
            rank=score.rank,
            clear_lamp=score.clear_lamp,
            combo_lamp=score.combo_lamp,
            chain_lamp=score.chain_lamp,
            max_combo=score.max_combo,
            judgements=score.judgements,
            note_percentage=score.note_percentage,
            achieved_at=score.achieved_at,
            rating=score.rating,
            ongeki_rating=score.ongeki_rating,
            ongeki_platinum_rating=score.ongeki_platinum_rating,
            overpower=score.overpower,
            _memo=score._memo,
        )


@dataclass(slots=True, kw_only=True)
class RecentScore(Score):
    track_no: int | None = None
    is_new_record: bool | None = None

    character: str | None = None
    skill: Skill | None = None
    skill_result: int | None = None

    @classmethod
    def from_score(cls, score: Score) -> Self:
        return cls(
            song=score.song,
            chart=score.chart,
            score=score.score,
            rank=score.rank,
            clear_lamp=score.clear_lamp,
            combo_lamp=score.combo_lamp,
            chain_lamp=score.chain_lamp,
            max_combo=score.max_combo,
            judgements=score.judgements,
            note_percentage=score.note_percentage,
            achieved_at=score.achieved_at,
            rating=score.rating,
            ongeki_rating=score.ongeki_rating,
            ongeki_platinum_rating=score.ongeki_platinum_rating,
            overpower=score.overpower,
            _memo=score._memo,
        )


@dataclass(slots=True, kw_only=True)
class CourseRecord:
    id: int
    cls: CourseClass
    name: str
    score: int
    rank: Rank
    clear_lamp: ClearLamp
    combo_lamp: ComboLamp
