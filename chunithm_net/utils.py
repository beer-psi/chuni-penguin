import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import msgspec
from bs4.element import ResultSet, Tag

from chunithm_net.models.player_data import Title

from .models.enums import ChainType, ClearType, ComboType, Difficulty, Rank

RE_CSS_BACKGROUND_IMAGE = re.compile(
    r"background-image\s*:\s*url\(['\"]?(?P<url>.+?)['\"]?\)"
)


class SpecialTitle(msgspec.Struct):
    content: str
    rarity: str


with (Path(__file__).parent / "assets" / "titles.json").open(encoding="utf-8") as f:
    SPECIAL_TITLES = msgspec.json.decode(f.read(), type=dict[str, SpecialTitle])


def chuni_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_player_rating(soup: ResultSet[Tag]) -> float:
    rating = ""
    for x in soup:
        digit = extract_last_part(cast(str, x["src"]))
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
            return Difficulty.BASIC
        case "advanced":
            return Difficulty.ADVANCED
        case "expert":
            return Difficulty.EXPERT
        case "master":
            return Difficulty.MASTER
        case "worldsend":
            return Difficulty.WORLDS_END
        case "ultima":
            return Difficulty.ULTIMA
        case "ultimate":
            return Difficulty.ULTIMA

        case _:
            msg = f"Unknown difficulty: {url}"
            raise ValueError(msg)


def get_rank_and_lamps(soup: Tag) -> tuple[Rank, ClearType, ComboType, ChainType]:
    if (rank_img_elem := soup.select_one("img[src*=_rank_]")) is not None:
        rank_img_url = cast(str, rank_img_elem["src"])
        rank = Rank(int(extract_last_part(rank_img_url)))
    else:
        rank = Rank.D

    if soup.select_one("img[src*=clear]") is not None:
        clear_type = ClearType.CLEAR
    elif soup.select_one("img[src*=hard]") is not None:
        clear_type = ClearType.HARD
    elif soup.select_one("img[src*=absolute]") is not None:
        clear_type = ClearType.ABSOLUTE
    elif soup.select_one("img[src*=brave]") is not None:
        clear_type = ClearType.BRAVE
    elif soup.select_one("img[src*=catastrophy]") is not None:
        clear_type = ClearType.CATASTROPHY
    else:
        clear_type = ClearType.FAILED

    if soup.select_one("img[src*=fullchain2]") is not None:
        chain_type = ChainType.FULL_CHAIN
    elif soup.select_one("img[src*=fullchain]") is not None:
        chain_type = ChainType.FULL_CHAIN_PLUS
    else:
        chain_type = ChainType.NONE

    # FC and AJ should override all other lamps.
    if soup.select_one("img[src*=fullcombo]") is not None:
        combo_type = ComboType.FULL_COMBO
    elif soup.select_one("img[src*=alljusticecritical]") is not None:
        combo_type = ComboType.ALL_JUSTICE_CRITICAL
    elif soup.select_one("img[src*=alljustice]") is not None:
        combo_type = ComboType.ALL_JUSTICE
    else:
        combo_type = ComboType.NONE

    return rank, clear_type, combo_type, chain_type


def get_course_rank_and_lamps(soup: Tag):
    if (rank_img_elem := soup.select_one("img[src*=_rank_]")) is not None:
        rank_img_url = cast(str, rank_img_elem["src"])
        rank = Rank(int(extract_last_part(rank_img_url)))
    else:
        rank = Rank.D

    if soup.select_one("img[src*=course_clear]") is not None:
        clear_type = ClearType.CLEAR
    else:
        clear_type = ClearType.FAILED

    if soup.select_one("img[src*=fullcombo]") is not None:
        combo_type = ComboType.FULL_COMBO
    elif soup.select_one("img[src*=alljusticecritical]") is not None:
        combo_type = ComboType.ALL_JUSTICE_CRITICAL
    elif soup.select_one("img[src*=alljustice]") is not None:
        combo_type = ComboType.ALL_JUSTICE
    else:
        combo_type = ComboType.NONE

    return rank, clear_type, combo_type


def parse_titles(title_elems: Sequence[Tag]):
    titles: list[Title] = []

    for title_elem in title_elems:
        title_style = title_elem.get("style")

        if title_style is None:
            continue

        title_background_url_match = RE_CSS_BACKGROUND_IMAGE.search(str(title_style))

        if title_background_url_match is None:
            continue

        title_background_url: str = title_background_url_match.group("url")
        title_background_url_filename = title_background_url.split("/")[-1]

        # regular title
        if title_background_url_filename.startswith("honor_bg_"):
            title_content_elem = title_elem.select_one(".player_honor_text span")

            if title_content_elem is None:
                msg = "Invalid title (missing title content on normal titles)"
                raise ValueError(msg)

            content = title_content_elem.get_text()
            rarity = extract_last_part(title_background_url_filename)
        elif title_background_url_filename in SPECIAL_TITLES:
            content = SPECIAL_TITLES[title_background_url_filename].content
            rarity = SPECIAL_TITLES[title_background_url_filename].rarity
        else:
            continue

        titles.append(Title(content, rarity))

    return titles
