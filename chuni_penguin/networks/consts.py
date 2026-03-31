from decimal import Decimal

from .types import Genre, TypePairedDictKey

KEY_SONG_ID = TypePairedDictKey[int]("SONG_ID")
KEY_SONG_VERSION = TypePairedDictKey[str]("SONG_VERSION")
KEY_SONG_GENRE = TypePairedDictKey[Genre]("SONG_GENRE")
KEY_LEVEL = TypePairedDictKey[str]("LEVEL")
KEY_INTERNAL_LEVEL = TypePairedDictKey[float]("INTERNAL_LEVEL")
KEY_PLAY_RATING = TypePairedDictKey[Decimal]("PLAY_RATING")
KEY_PLATINUM_RATING = TypePairedDictKey[Decimal]("PLATINUM_RATING")
KEY_OVERPOWER = TypePairedDictKey[Decimal]("OVERPOWER_BASE")
KEY_OVERPOWER_MAX = TypePairedDictKey[Decimal]("OVERPOWER_MAX")
KEY_TOTAL_COMBO = TypePairedDictKey[int]("TOTAL_COMBO")
