import json

import httpx
import httpx_aiohttp
import msgspec
from structlog.stdlib import BoundLogger

from .seeds import SEEDS_DIR, SeedsJSONEncoder


async def update_tachi(logger: BoundLogger):
    with (SEEDS_DIR / "songs.json").open("rb") as f:
        songs = msgspec.json.decode(f.read())

    charts_by_id_difficulty = {}

    for song in songs:
        mapping = charts_by_id_difficulty[song["id"]] = {}

        for chart in song["charts"]:
            mapping[chart["difficulty"]] = chart

    async with httpx.AsyncClient(
        transport=httpx_aiohttp.AIOHTTPTransport(retries=5)
    ) as client:
        resp = await client.get(
            "https://raw.githubusercontent.com/zkldi/Tachi/refs/heads/main/db/seeds/charts-chunithm.json"
        )
        tachi_charts = resp.json()

    for tachi_chart in tachi_charts:
        if isinstance(tachi_chart["data"]["inGameID"], int):
            in_game_ids = [tachi_chart["data"]["inGameID"]]
        elif isinstance(tachi_chart["data"]["inGameID"], list):
            in_game_ids = tachi_chart["data"]["inGameID"]
        else:
            msg = f"Unknown inGameID list type {type(tachi_chart['data']['inGameID'])}"
            raise TypeError(msg)

        for in_game_id in in_game_ids:
            mapping = charts_by_id_difficulty.get(in_game_id)

            if mapping is None:
                continue

            if in_game_id >= 8000:
                chart = mapping.get("WE")
            else:
                chart = mapping.get(tachi_chart["difficulty"][:3])

            if chart is None:
                continue

            chart["tachi_chart_id"] = tachi_chart["id"]

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )
