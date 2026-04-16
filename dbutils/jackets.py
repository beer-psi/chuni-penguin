import json
import re
from typing import Any

import httpx
import httpx_aiohttp
import msgspec
from structlog.stdlib import BoundLogger

from chuni_penguin.config import config
from chuni_penguin.constants import ASSETS_DIR, INTERNATIONAL_JACKET_BASE, JACKET_BASE

from .chunirec import ChunithmOfficialSong, MaimaiOfficialSong
from .seeds import SEEDS_DIR, SeedsJSONEncoder

# There's this really stupid thing where CHUNITHM/ONGEKI has the original game name
# in the artist for songs from other IPs, but maimai doesn't. For song title/artist lookup
# to work properly across all games, we need to strip the original game name from the artist.
RE_GAME_NAME = re.compile(r"「.+」$")


class ZetarakuSong(msgspec.Struct, rename="camel"):
    title: str
    artist: str
    category: str
    image_name: str


class ZetarakuData(msgspec.Struct):
    songs: list[ZetarakuSong]


def is_url(value: str):
    return value.startswith(("http://", "https://"))


def normalize_artist(artist: str):
    return (
        RE_GAME_NAME.sub("", artist)
        # Really dumb edge case, thanks SEGA.
        # The alpha character used by maimai DX is APL FUNCTIONAL SYMBOL ALPHA (U+237A).
        # The alpha character used by CHUNITHM and O.N.G.E.K.I. is GREEK SMALL LETTER ALPHA (U+03B1).
        # This is why cross c>compare doesn't work with maimai bots.
        .replace("からとP⍺ոchii少年", "からとPαnchii少年")  # noqa: RUF001
        .rstrip()
    )


async def update_jackets(logger: BoundLogger):
    client = httpx.AsyncClient(transport=httpx_aiohttp.AIOHTTPTransport(retries=5))
    song_title_artist_lookup: dict[str, dict[str, Any]] = {}

    with (SEEDS_DIR / "songs.json").open("rb") as f:
        songs = msgspec.json.decode(f.read())

    songs_by_id = {s["id"]: s for s in songs}

    official_chunithm_resp = await client.get(
        "https://chunithm.sega.jp/storage/json/music.json"
    )

    official_chunithm = msgspec.json.decode(
        official_chunithm_resp.content,
        type=list[ChunithmOfficialSong],
        strict=False,
    )
    official_chunithm_by_id = {x.id: x for x in official_chunithm}

    for song in songs:
        if song["id"] < 8000:
            song_title_artist_lookup[
                f"{song['title']}:{normalize_artist(song['artist'])}"
            ] = song

        existing_jackets = set(song["jackets"])

        if song["jacket"] is None:
            if song["id"] not in official_chunithm_by_id:
                continue
            song["jacket"] = official_chunithm_by_id[song["id"]].image

        if is_url(song["jacket"]) and song["jacket"] not in existing_jackets:
            song["jackets"].append(song["jacket"])
        else:
            for url in (
                f"{JACKET_BASE}/{song['jacket']}",
                f"{INTERNATIONAL_JACKET_BASE}/{song['jacket']}",
            ):
                if url not in existing_jackets:
                    song["jackets"].append(url)

    for game in ("maimai", "chunithm", "ongeki"):
        zetaraku_songs_resp = await client.get(
            f"https://dp4p6x0xfi5o9.cloudfront.net/{game}/data.json"
        )
        zetaraku_songs = msgspec.json.decode(
            zetaraku_songs_resp.content, type=ZetarakuData
        )

        for song in zetaraku_songs.songs:
            # We are not doing jacket song lookups for WORLD'S END/LUNATIC automatically because
            # holy fuck it's a massive can of worms.
            if song.category in ("WORLD'S END", "LUNATIC"):
                continue

            search_key = song.title + ":" + normalize_artist(song.artist)

            if (db_song := song_title_artist_lookup.get(search_key)) is None:
                continue

            logger.info(
                f"Mapped {db_song['artist']} - {db_song['title']} to Zetaraku {game} entry {song.artist} - {song.title}."
            )

            url = f"https://dp4p6x0xfi5o9.cloudfront.net/{game}/img/cover/{song.image_name}"

            if url not in db_song["jackets"]:
                db_song["jackets"].append(url)

    official_maimai_resp = await client.get(
        "https://maimai.sega.jp/data/maimai_songs.json"
    )
    official_maimai = msgspec.json.decode(
        official_maimai_resp.content,
        type=list[MaimaiOfficialSong],
    )

    for song in official_maimai:
        search_key = song.title + ":" + normalize_artist(song.artist)

        if (db_song := song_title_artist_lookup.get(search_key)) is None:
            continue

        logger.info(
            f"Mapped {db_song['artist']} - {db_song['title']} to official maimai entry {song.artist} - {song.title}."
        )

        existing_jackets = set(db_song["jackets"])

        for url in (
            f"https://maimaidx.jp/maimai-mobile/img/Music/{song.image_url}",
            f"https://maimaidx-eng.com/maimai-mobile/img/Music/{song.image_url}",
            f"https://mimixd.app/images/render/cover/{song.image_url}",
        ):
            if url not in existing_jackets:
                db_song["jackets"].append(url)

    if config.web.serve_assets and config.web.base_url:
        for jacket in (ASSETS_DIR / "jackets").iterdir():
            if not jacket.stem.isdigit():
                continue

            song_id = int(jacket.stem)
            url = f"{config.web.base_url}/assets/jackets/{jacket.name}"

            if song_id in songs_by_id and url not in songs_by_id[song_id]["jackets"]:
                songs_by_id[song_id]["jackets"].append(url)

    with (SEEDS_DIR / "songs.json").open("w") as f:
        json.dump(
            songs,
            f,
            cls=SeedsJSONEncoder,
            indent=4,
            ensure_ascii=False,
        )

    await client.aclose()
