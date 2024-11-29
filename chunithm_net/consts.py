from decimal import Decimal

from chunithm_net.models.record import DetailedParams
from chunithm_net.models.type_paired_dict import TypePairedDictKey

JACKET_BASE = "https://new.chunithm-net.com/chuni-mobile/html/mobile/img"
INTERNATIONAL_JACKET_BASE = "https://chunithm-net-eng.com/mobile/img"

_KEY_DETAILED_PARAMS = TypePairedDictKey[DetailedParams]()
KEY_SONG_ID = TypePairedDictKey[int]()
KEY_SONG_VERSION = TypePairedDictKey[str]()
KEY_LEVEL = TypePairedDictKey[str]()
KEY_INTERNAL_LEVEL = TypePairedDictKey[float]()
KEY_PLAY_RATING = TypePairedDictKey[Decimal]()
KEY_OVERPOWER_BASE = TypePairedDictKey[Decimal]()
KEY_OVERPOWER_MAX = TypePairedDictKey[Decimal]()
KEY_TOTAL_COMBO = TypePairedDictKey[int]()
