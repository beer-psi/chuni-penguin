from chuni_penguin.networks.types import LinkedGate, LinkedGateStatus, TypePairedDictKey

JACKET_BASE = "https://new.chunithm-net.com/chuni-mobile/html/mobile/img"
INTERNATIONAL_JACKET_BASE = "https://chunithm-net-eng.com/mobile/img"
LINKED_VERSE_PROGRESS_BADGES: dict[str, tuple[LinkedGate | None, LinkedGateStatus]] = {
    "Y9BRPL5DR4EDEOH06QV5OUPD2WYFF14I": (LinkedGate.origin, LinkedGateStatus.not_found),
    "WVJF8TJO9A8D4NHZRWBEXW3Z4MTUG6GZ": (
        LinkedGate.origin,
        LinkedGateStatus.under_analysis,
    ),
    "IUQ44T4AXQKGSRWGWUSJDF0HMQ4ANMQ9": (LinkedGate.origin, LinkedGateStatus.linkable),
    "HB8EY2I5ZC3N5L881RKFWG5G7BR7D56N": (LinkedGate.origin, LinkedGateStatus.clear),
    "EJ7LIQ0AFC5PMVJQY4UFIR9D961OZEMT": (LinkedGate.air, LinkedGateStatus.not_found),
    "LMKHADUSGGZBVGVWUWZ0KDX476FXN07H": (
        LinkedGate.air,
        LinkedGateStatus.under_analysis,
    ),
    "43CM9OC9J34RXAQ4N24PFS7ZTI1W4X8Z": (LinkedGate.air, LinkedGateStatus.linkable),
    "TU4SRWXCY1OKDO4R0HW8CLXR4UGWOALL": (LinkedGate.air, LinkedGateStatus.clear),
    "A1JQ45K97ZIB50JONO302LDV9OKZ96KC": (LinkedGate.star, LinkedGateStatus.not_found),
    "A0YQIQFHIYWS39NTVBUT4MAC2SZ9OGNV": (
        LinkedGate.star,
        LinkedGateStatus.under_analysis,
    ),
    "K358WG6QFX2Q5CVVFCSUXKR42TQLOOGM": (LinkedGate.star, LinkedGateStatus.linkable),
    "VRMAQKZAFXWXBH9LK768FDYFV2AJUA7A": (LinkedGate.star, LinkedGateStatus.clear),
    "IB6KI2OFKMIJ2KPCH3JWS8OKJQ69J5QQ": (LinkedGate.amazon, LinkedGateStatus.not_found),
    "2VUVKET50AOXQD0RAQ3SMFBVP7YTPGOO": (
        LinkedGate.amazon,
        LinkedGateStatus.under_analysis,
    ),
    "O2R15SSPWS2JYGF1U6GDUMW3UW7K0A11": (LinkedGate.amazon, LinkedGateStatus.linkable),
    "FTDY9GBIZERC5J9VZN882WFMKFLCIEZ7": (LinkedGate.amazon, LinkedGateStatus.clear),
    "YRI8UKP26A4F4G810VAYZW9T9SXO49BP": (
        LinkedGate.crystal,
        LinkedGateStatus.not_found,
    ),
    "9Q6I0MKPUYRL3MMG191BR5I45JREKO7M": (
        LinkedGate.crystal,
        LinkedGateStatus.under_analysis,
    ),
    "P09LZYXJHAG7F78TE43DGH826GAD2H2C": (LinkedGate.crystal, LinkedGateStatus.linkable),
    "TEFG9MDNMX2X5IYPRYJYCUDNC8X3E49U": (LinkedGate.crystal, LinkedGateStatus.clear),
    # They reuse the same not_found badge from CRYSTAL for PARADISE for some reason?
    "TCMI6URY6CA2DZGOPNQ13KRE1A8V3UC8": (LinkedGate.new, LinkedGateStatus.not_found),
    "QF07NCIW9AQKZOUF2OXP0MWLWG1BLBCM": (LinkedGate.sun, LinkedGateStatus.not_found),
    "7FFQEALW1J8TXTOG2ONB6PHPNA2252Q2": (
        LinkedGate.luminous,
        LinkedGateStatus.not_found,
    ),
    "2VG92AY9AH7IX5UQF3HK4HHDAOFJLQ9I": (LinkedGate.verse, LinkedGateStatus.not_found),
}

_KEY_DETAILED_PARAMS_IDX = TypePairedDictKey[int]("_DETAILED_PARAMS")
