from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import ChainLamp, ClearLamp, ComboLamp, Difficulty, Rank
from .typeddict import TypePairedDict

MISSING: Any = object()


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


@dataclass(slots=True, kw_only=True)
class PersonalBest(Score):
    play_count: int | None = None
    ajc_count: int | None = None

    @classmethod
    def from_score(cls, score: Score):
        return cls(
            title=score.title,
            difficulty=score.difficulty,
            score=score.score,
            jacket_url=score.jacket_url,
            rank=score.rank,
            clear_lamp=score.clear_lamp,
            combo_lamp=score.combo_lamp,
            chain_lamp=score.chain_lamp,
            achieved_at=score.achieved_at,
            max_combo=score.max_combo,
            judgements=score.judgements,
            note_percentage=score.note_percentage,
            extras=score.extras,
            play_count=None,
            ajc_count=None,
        )


@dataclass(slots=True, kw_only=True)
class RecentScore(Score):
    track_no: int | None = None
    is_new_record: bool | None = None

    character: str | None = None
    skill: Skill | None = None
    skill_result: int | None = None

    @classmethod
    def from_score(cls, score: Score):
        return cls(
            title=score.title,
            difficulty=score.difficulty,
            score=score.score,
            jacket_url=score.jacket_url,
            rank=score.rank,
            clear_lamp=score.clear_lamp,
            combo_lamp=score.combo_lamp,
            chain_lamp=score.chain_lamp,
            achieved_at=score.achieved_at,
            max_combo=score.max_combo,
            judgements=score.judgements,
            note_percentage=score.note_percentage,
            extras=score.extras,
            track_no=None,
            is_new_record=None,
            character=None,
            skill=None,
            skill_result=None,
        )
