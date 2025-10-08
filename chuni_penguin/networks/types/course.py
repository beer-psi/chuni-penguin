from dataclasses import dataclass

from .enums import ClearLamp, ComboLamp, CourseClass, Rank


@dataclass(kw_only=True)
class CourseRecord:
    id: int
    cls: CourseClass
    name: str
    score: int
    rank: Rank
    clear_lamp: ClearLamp
    combo_lamp: ComboLamp
