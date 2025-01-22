import re
from logging import Logger
from typing import TypedDict

import httpx
import msgspec
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chunithm_net.consts import INTERNATIONAL_JACKET_BASE, JACKET_BASE
from database.models import Song, SongJacket

from .chunirec import ChunithmOfficialSong, MaimaiOfficialSong

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


class SongJacketInsertCols(TypedDict):
    song_id: int
    jacket_url: str


def is_url(value: str):
    return value.startswith(("http://", "https://"))


def normalize_artist(artist: str):
    return (
        RE_GAME_NAME
        .sub("", artist)
        # Really dumb edge case, thanks SEGA.
        # The alpha character used by maimai DX is APL FUNCTIONAL SYMBOL ALPHA (U+237A).
        # The alpha character used by CHUNITHM and O.N.G.E.K.I. is GREEK SMALL LETTER ALPHA (U+03B1).
        # This is why cross c>compare doesn't work with maimai bots.
        .replace("からとP⍺ոchii少年", "からとPαnchii少年")
        .rstrip()
    )


async def update_jackets(
    logger: Logger, async_session: async_sessionmaker[AsyncSession]
):
    client = httpx.AsyncClient()

    jackets: list[SongJacketInsertCols] = []
    song_title_artist_lookup: dict[str, Song] = {}

    async with async_session() as session:
        songs = (await session.scalars(select(Song))).all()

    official_jacket_updates = []
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
        if song.id < 8000:
            song_title_artist_lookup[
                f"{song.title}:{normalize_artist(song.artist)}"
            ] = song

        if song.jacket is None:
            if song.id not in official_chunithm_by_id:
                continue
            song.jacket = official_chunithm_by_id[song.id].image
            official_jacket_updates.append({"id": song.id, "jacket": song.jacket})

        if is_url(song.jacket):
            jackets.append({"song_id": song.id, "jacket_url": song.jacket})
        else:
            jackets.append(
                {
                    "song_id": song.id,
                    "jacket_url": f"{JACKET_BASE}/{song.jacket}",
                }
            )
            jackets.append(
                {
                    "song_id": song.id,
                    "jacket_url": f"{INTERNATIONAL_JACKET_BASE}/{song.jacket}",
                }
            )

    if len(official_jacket_updates) > 0:
        async with async_session() as session:
            await session.execute(update(Song), official_jacket_updates)
            await session.commit()

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
                f"Mapped {db_song.artist} - {db_song.title} to Zetaraku {game} entry {song.artist} - {song.title}."
            )

            jackets.append(
                {
                    "song_id": db_song.id,
                    "jacket_url": f"https://dp4p6x0xfi5o9.cloudfront.net/{game}/img/cover/{song.image_name}",
                }
            )

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
            f"Mapped {db_song.artist} - {db_song.title} to official maimai entry {song.artist} - {song.title}."
        )

        jackets.append(
            {
                "song_id": db_song.id,
                "jacket_url": f"https://maimaidx.jp/maimai-mobile/img/Music/{song.image_url}",
            }
        )
        jackets.append(
            {
                "song_id": db_song.id,
                "jacket_url": f"https://maimaidx-eng.com/maimai-mobile/img/Music/{song.image_url}",
            }
        )

    async with async_session() as session:
        logger.info("Upserting %d jacket URLs.", len(jackets))

        insert_stmt = insert(SongJacket)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[SongJacket.jacket_url],
            set_={
                "song_id": insert_stmt.excluded.song_id,
            },
        )
        await session.execute(upsert_stmt, jackets)
        await session.commit()

    await client.aclose()
