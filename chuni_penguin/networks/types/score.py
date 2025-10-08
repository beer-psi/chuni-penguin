from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import ChainLamp, ClearLamp, ComboLamp, Difficulty, Rank
from .typeddict import TypePairedDict

MISSING: Any = object()


@dataclass(kw_only=True)
class Judgements:
    justice_heaven: int | None = None
    justice_critical: int
    justice: int
    attack: int
    miss: int


@dataclass(kw_only=True)
class NotePercentage:
    tap: float
    hold: float
    slide: float
    air: float
    flick: float


@dataclass(kw_only=True)
class Skill:
    name: str
    grade: int | None


@dataclass(kw_only=True)
class Score:
    title: str
    difficulty: Difficulty
    score: int
    jacket_url: str | None = None

    rank: Rank = MISSING
    clear_lamp: ClearLamp
    combo_lamp: ComboLamp
    chain_lamp: ChainLamp | None = None

    achieved_at: datetime | None = None

    max_combo: int | None = None
    judgements: Judgements | None = None
    note_percentage: NotePercentage | None = None

    extras: TypePairedDict = field(default_factory=TypePairedDict)

    def __post_init__(self):
        if self.rank is MISSING or self.rank == Rank.d:
            self.rank = Rank.from_score(self.score)


@dataclass(kw_only=True)
class PersonalBest(Score):
    play_count: int | None = None
    ajc_count: int | None = None


@dataclass(kw_only=True)
class RecentScore(Score):
    track_no: int | None = None
    is_new_record: bool | None = None

    character: str | None = None
    skill: Skill | None = None
    skill_result: int | None = None
