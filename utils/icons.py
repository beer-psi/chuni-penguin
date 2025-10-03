from typing import TYPE_CHECKING, overload

from utils.config import config

if TYPE_CHECKING:
    from chunithm_net.models.enums import Rank


@overload
def get_icon(named: str) -> str | None: ...


@overload
def get_icon(named: str, fallback: str) -> str: ...


def get_icon(named: str, fallback: str | None = None) -> str | None:
    return getattr(config.icons, named, fallback)


def rank_icon(rank: "str | Rank") -> str:
    str_rank = str(rank)
    key = str_rank.lower().replace("+", "p")
    return get_icon(key, str_rank)
