try:
    from discord.enums import Enum
except ImportError:
    from enum import Enum


class ClearLamp(Enum):
    failed = 0
    clear = 1
    hard = 4
    brave = 5
    absolute = 6
    catastrophy = 7

    def __str__(self):
        return self.name.upper()

    def short(self) -> str:
        if self == ClearLamp.failed:
            return "FAILED"
        if self == ClearLamp.clear:
            return "CLR"
        if self == ClearLamp.hard:
            return "HRD"
        if self == ClearLamp.brave:
            return "BRV"
        if self == ClearLamp.absolute:
            return "ABS"
        if self == ClearLamp.catastrophy:
            return "CTS"

        msg = f"{self!r} is not a valid {self.__class__.__name__}"
        raise ValueError(msg)


class ComboLamp(Enum):
    none = 0
    full_combo = 1
    all_justice = 2
    all_justice_critical = 3

    def __str__(self):
        if self == ComboLamp.all_justice_critical:
            return "AJC"

        return self.name.upper().replace("_", " ")

    def short(self) -> str:
        if self == ComboLamp.all_justice_critical:
            return "AJC"
        if self == ComboLamp.all_justice:
            return "AJ"
        if self == ComboLamp.full_combo:
            return "FC"

        return "NONE"


class ChainLamp(Enum):
    none = 0
    # Yes, this is intentional, since full chain lamp was added after full chain+.
    full_chain = 2
    full_chain_plus = 1

    def __str__(self):
        if self == ChainLamp.full_chain_plus:
            return "FULL CHAIN+"

        return self.name.upper().replace("_", " ")

    def short(self) -> str:
        if self == ChainLamp.full_chain:
            return "FCH"
        if self == ChainLamp.full_chain_plus:
            return "FCH+"

        return "NONE"
