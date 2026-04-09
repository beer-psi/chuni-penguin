import string
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from selectolax.lexbor import LexborNode

from chuni_penguin.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Difficulty,
    Rank,
)

COOKIE_CHARACTERS = f"{string.ascii_lowercase}{string.digits}"


def is_valid_clal(clal: str) -> bool:
    if clal.startswith("clal="):
        clal = clal[5:]

    return len(clal) == 64 and all(c in COOKIE_CHARACTERS for c in clal)


def chuni_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_player_rating(soup: list[LexborNode]) -> float:
    rating = ""
    for x in soup:
        digit = extract_last_part(cast(str, x.attrs["src"]))
        if digit == "comma":
            rating += "."
        else:
            rating += digit[1]
    return float(rating)


def parse_time(time: str, format: str = "%Y/%m/%d %H:%M") -> datetime:
    return datetime.strptime(time, format).replace(tzinfo=ZoneInfo("Asia/Tokyo"))


def extract_last_part(url: str) -> str:
    return url.split("_")[-1].split(".")[0]


def difficulty_from_imgurl(url: str) -> Difficulty:
    match extract_last_part(url):
        case "basic":
            return Difficulty.basic
        case "advanced":
            return Difficulty.advanced
        case "expert":
            return Difficulty.expert
        case "master":
            return Difficulty.master
        case "worldsend":
            return Difficulty.worlds_end
        case "ultima":
            return Difficulty.ultima
        case "ultimate":
            return Difficulty.ultima

        case _:
            msg = f"Unknown difficulty: {url}"
            raise ValueError(msg)


def get_rank_and_lamps(
    soup: LexborNode,
) -> tuple[Rank, ClearLamp, ComboLamp, ChainLamp]:
    if (rank_img_elem := soup.css_first("img[src*=_rank_]")) is not None:
        rank_img_url = cast(str, rank_img_elem.attrs["src"])
        rank = Rank(int(extract_last_part(rank_img_url)))
    else:
        rank = Rank.d

    if soup.css_first("img[src*=clear]") is not None:
        clear_type = ClearLamp.clear
    elif soup.css_first("img[src*=hard]") is not None:
        clear_type = ClearLamp.hard
    elif soup.css_first("img[src*=absolute]") is not None:
        clear_type = ClearLamp.absolute
    elif soup.css_first("img[src*=brave]") is not None:
        clear_type = ClearLamp.brave
    elif soup.css_first("img[src*=catastrophy]") is not None:
        clear_type = ClearLamp.catastrophy
    else:
        clear_type = ClearLamp.failed

    if soup.css_first("img[src*=fullchain2]") is not None:
        chain_type = ChainLamp.full_chain
    elif soup.css_first("img[src*=fullchain]") is not None:
        chain_type = ChainLamp.full_chain_plus
    else:
        chain_type = ChainLamp.none

    # FC and AJ should override all other lamps.
    if soup.css_first("img[src*=fullcombo]") is not None:
        combo_type = ComboLamp.full_combo
    elif soup.css_first("img[src*=alljusticecritical]") is not None:
        combo_type = ComboLamp.all_justice_critical
    elif soup.css_first("img[src*=alljustice]") is not None:
        combo_type = ComboLamp.all_justice
    else:
        combo_type = ComboLamp.none

    return rank, clear_type, combo_type, chain_type


def get_course_rank_and_lamps(soup: LexborNode):
    if (rank_img_elem := soup.css_first("img[src*=_rank_]")) is not None:
        rank_img_url = cast(str, rank_img_elem.attrs["src"])
        rank = Rank(int(extract_last_part(rank_img_url)))
    else:
        rank = Rank.d

    if soup.css_first("img[src*=course_clear]") is not None:
        clear_type = ClearLamp.clear
    else:
        clear_type = ClearLamp.failed

    if soup.css_first("img[src*=fullcombo]") is not None:
        combo_type = ComboLamp.full_combo
    elif soup.css_first("img[src*=alljusticecritical]") is not None:
        combo_type = ComboLamp.all_justice_critical
    elif soup.css_first("img[src*=alljustice]") is not None:
        combo_type = ComboLamp.all_justice
    else:
        combo_type = ComboLamp.none

    return rank, clear_type, combo_type
