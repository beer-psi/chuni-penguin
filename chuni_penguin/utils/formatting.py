from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from discord.utils import escape_markdown

from chuni_penguin.networks.chunithm_net import INTERNATIONAL_JACKET_BASE, JACKET_BASE
from chuni_penguin.networks.types import Difficulty

if TYPE_CHECKING:
    from chuni_penguin.database import Alias, SdvxinChartView, Song


def did_you_mean_text(
    prefix: str | None, result: "Song | None", alias: "Alias | None"
) -> str:
    from chuni_penguin.config import config

    did_you_mean = ""

    if result is not None:
        did_you_mean = f"Did you mean **{escape_markdown(result.title)}**?"
        if alias is not None:
            did_you_mean = f"Did you mean **{escape_markdown(alias.alias)}** (for **{escape_markdown(result.title)}**)?"

    reply = f"No songs found. {did_you_mean}".strip()

    if did_you_mean:
        reply += f"\n(You can also use `{prefix or config.bot.default_prefix}alias add <title> <alias>` to add the alias for this server.)"

    return reply


def yt_search_link(title: str, difficulty: str) -> str:
    try:
        diff = Difficulty(difficulty)
        difficulty = str(diff)
    except ValueError:
        pass

    return "https://www.youtube.com/results?search_query=" + quote(
        f"CHUNITHM {title} {difficulty}"
    )


def get_jacket_url(song: "Song") -> str | None:
    from chuni_penguin.config import config

    current_time = datetime.now(ZoneInfo("Asia/Tokyo"))
    is_maintenance = 4 <= current_time.hour <= 7

    if song.jacket is not None:
        if song.available and not is_maintenance:
            return f"{INTERNATIONAL_JACKET_BASE}/{song.jacket}"

        if not song.removed:
            return f"{JACKET_BASE}/{song.jacket}"

    if config.web.serve_assets and config.web.base_url is not None:
        url = httpx.URL(config.web.base_url)

        if url.host.startswith("127.") or url.host == "localhost":
            return song.jacket

        return f"{config.web.base_url}/assets/jackets/{song.id}.webp"

    return song.jacket


def sdvxin_link(view: "SdvxinChartView") -> str:
    id = str(view.id)
    difficulty = view.difficulty

    if "ULT" not in difficulty and "WE" not in difficulty:
        if difficulty == "MAS":
            difficulty = "MST"
        elif difficulty == "BAS":
            difficulty = "BSC"
        return f"https://sdvx.in/chunithm/{id[:2]}/{id}{difficulty.lower()}.htm"

    difficulty = difficulty.replace("WE", "end").lower()
    return f"https://sdvx.in/chunithm/{difficulty[:3]}/{id}{difficulty}{view.end_index or ''}.htm"


def bold(content: Any) -> str:
    return f"**{content}**"


def bold_if(condition: bool, content: Any) -> str | Any:  # noqa: FBT001
    return f"**{content}**" if condition else content
