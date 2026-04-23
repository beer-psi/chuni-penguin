from chuni_penguin.types import LinkedGate, LinkedGateStatus

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
    "TCMI6URY6CA2DZGOPNQ13KRE1A8V3UC8": (
        LinkedGate.paradise,
        LinkedGateStatus.not_found,
    ),
    "DEYNZGCQYL3JD92F3CN6T5SDCC8FOM84": (
        LinkedGate.paradise,
        LinkedGateStatus.under_analysis,
    ),
    "BT1DOY9LQFQGG712ZZ2LIU8UZCID5X23": (
        LinkedGate.paradise,
        LinkedGateStatus.linkable,
    ),
    "GBJ90ERPKKNSJXO7O5P6IRP9QAP8BYLO": (LinkedGate.paradise, LinkedGateStatus.clear),
    "DM77M8PZI6QBYYPZTGZRN3KVS7RUG6EI": (LinkedGate.new, LinkedGateStatus.not_found),
    "PFIGRBPAP4RH0HW6PHV6TLNBB5W6ESZ3": (
        LinkedGate.new,
        LinkedGateStatus.under_analysis,
    ),
    "ZTCCYKHBRB0DOO9IZRDIQO6CKY7R7HSY": (LinkedGate.new, LinkedGateStatus.linkable),
    "MVYAA3OTYDT5369W0KH86KG28XX07K70": (LinkedGate.new, LinkedGateStatus.clear),
    "5SG4USIH41QX722D5G11CBMS292Z13PN": (None, LinkedGateStatus.not_found),
}
