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
            "https://raw.githubusercontent.com/zkrising/Tachi/main/seeds/collections/charts-chunithm.json"
        )
        tachi_charts = resp.json()

    for tachi_chart in tachi_charts:
        mapping = charts_by_id_difficulty.get(tachi_chart["data"]["inGameID"])

        if mapping is None:
            continue

        chart = mapping.get(tachi_chart["difficulty"][:3])

        if chart is None:
            continue

        chart["tachi_chart_id"] = tachi_chart["chartID"]

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )
