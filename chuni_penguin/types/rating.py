from dataclasses import dataclass
from decimal import Decimal

from .score import PersonalBest

try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class RatingType(Enum):
    in_game = 1
    naive = 2
    ongeki = 3
    ongeki_naive = 4

    def __str__(self):
        if self == RatingType.in_game:
            return "Rating"
        if self == RatingType.naive:
            return "NaiveRating"
        if self == RatingType.ongeki:
            return "O.N.G.E.K.I."
        if self == RatingType.ongeki_naive:
            return "O.N.G.E.K.I. Naive"

        msg = f"Unknown enum variant {self!r}"
        raise ValueError(msg)


class RatingFrameType(Enum):
    best = 1
    new = 2
    platinum = 3


@dataclass(slots=True, kw_only=True)
class RatingFrame:
    type: RatingFrameType
    num_scores: int
    scores: list[PersonalBest]


@dataclass(slots=True, kw_only=True)
class RatingBreakdown:
    rating: Decimal
    frames: dict[RatingFrameType, RatingFrame]


@dataclass(slots=True, kw_only=True)
class RatingSystem:
    """
    A rating system.
    """

    type: RatingType
    """
    The rating system.
    """

    value: float
    """
    The user's rating in the specified rating system.
    """

    max_value: float | None = None
    """
    The user's peak rating in the specified rating system.
    """
