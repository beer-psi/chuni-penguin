from decimal import Decimal

from chunithm_net.models.enums import Genres
from chunithm_net.models.record import DetailedParams
from chunithm_net.models.type_paired_dict import TypePairedDictKey

JACKET_BASE = "https://new.chunithm-net.com/chuni-mobile/html/mobile/img"
INTERNATIONAL_JACKET_BASE = "https://chunithm-net-eng.com/mobile/img"

_KEY_DETAILED_PARAMS = TypePairedDictKey[DetailedParams]("_DETAILED_PARAMS")
KEY_SONG_ID = TypePairedDictKey[int]("SONG_ID")
KEY_SONG_VERSION = TypePairedDictKey[str]("SONG_VERSION")
KEY_SONG_GENRE = TypePairedDictKey[Genres]("SONG_GENRE")
KEY_LEVEL = TypePairedDictKey[str]("LEVEL")
KEY_INTERNAL_LEVEL = TypePairedDictKey[float]("INTERNAL_LEVEL")
KEY_PLAY_RATING = TypePairedDictKey[Decimal]("PLAY_RATING")
KEY_OVERPOWER = TypePairedDictKey[Decimal]("OVERPOWER_BASE")
KEY_OVERPOWER_MAX = TypePairedDictKey[Decimal]("OVERPOWER_MAX")
KEY_TOTAL_COMBO = TypePairedDictKey[int]("TOTAL_COMBO")
