from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import ChainType, ClearType, ComboType, CourseClass, Difficulty, Rank
from .type_paired_dict import TypePairedDict


@dataclass
class Skill:
    name: str
    grade: Optional[int]


@dataclass
class Judgements:
    jcrit: int
    justice: int
    attack: int
    miss: int


@dataclass
class NoteType:
    tap: float
    hold: float
    slide: float
    air: float
    flick: float


@dataclass
class DetailedParams:
    idx: int
    token: str


@dataclass(kw_only=True)
class Record:
    title: str
    difficulty: Difficulty
    score: int

    rank: Rank = Rank.D
    clear_lamp: ClearType = ClearType.FAILED
    combo_lamp: ComboType = ComboType.NONE
    chain_lamp: ChainType = ChainType.NONE

    jacket: Optional[str] = None

    extras: TypePairedDict = field(default_factory=TypePairedDict)


@dataclass(kw_only=True)
class MusicRecord(Record):
    play_count: Optional[int] = None
    ajc_count: Optional[int] = None

    @staticmethod
    def from_record(record: Record) -> "MusicRecord":
        return MusicRecord(**record.__dict__, jacket="")


@dataclass(kw_only=True)
class RecentRecord(MusicRecord):
    track: int
    date: datetime
    new_record: bool


@dataclass(kw_only=True)
class DetailedRecentRecord(RecentRecord):
    character: str
    skill: Skill
    skill_result: int

    max_combo: int

    judgements: Judgements
    note_type: NoteType

    @staticmethod
    def from_basic(record: RecentRecord) -> "DetailedRecentRecord":
        return DetailedRecentRecord(
            **record.__dict__,
            character="",
            skill=Skill("", 0),
            skill_result=0,
            max_combo=0,
            judgements=Judgements(0, 0, 0, 0),
            note_type=NoteType(0, 0, 0, 0, 0),
        )


@dataclass(kw_only=True)
class CourseRecord:
    id: int
    cls: CourseClass
    name: str
    score: int
    rank: Rank
    clear_lamp: ClearType
    combo_lamp: ComboType
