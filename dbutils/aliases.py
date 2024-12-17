from logging import Logger

import aiohttp
import msgspec
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import Alias, Song


class TachiChunithmSongData(msgspec.Struct, rename="camel"):
    display_version: str
    genre: str


class TachiChunithmSong(msgspec.Struct, rename="camel"):
    alt_titles: list[str]
    artist: str
    data: TachiChunithmSongData
    id: int
    search_terms: list[str]
    title: str


async def update_aliases(
    logger: Logger, async_session: async_sessionmaker[AsyncSession]
):
    async with aiohttp.ClientSession() as client, async_session() as session, session.begin():
        resp = await client.get(
            "https://github.com/lomotos10/GCM-bot/raw/main/data/aliases/en/chuni.tsv"
        )
        tachi_resp = await client.get(
            "https://github.com/zkrising/Tachi/raw/main/seeds/collections/songs-chunithm.json"
        )
        aliases = [x.split("\t") for x in (await resp.text()).splitlines()]

        tachi_songs = msgspec.json.decode(
            await tachi_resp.read(), type=list[TachiChunithmSong]
        )
        aliases.extend([[x.title, *x.search_terms] for x in tachi_songs])

        inserted_aliases = []
        for alias in aliases:
            if len(alias) < 2:
                continue
            title = alias[0]

            song = (
                await session.execute(
                    select(Song)
                    # Limit to non-WE entries. WE entries are redirected to
                    # their non-WE respectives when song-searching anyways.
                    .where((Song.title == title) & (Song.id < 8000))
                )
            ).scalar_one_or_none()
            if song is None:
                continue

            inserted_aliases.extend(
                [
                    {"alias": x, "guild_id": -1, "song_id": song.id, "owner_id": None}
                    for x in alias[1:]
                ]
            )

        insert_statement = insert(Alias)
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[Alias.alias, Alias.guild_id],
            set_={"song_id": insert_statement.excluded.song_id},
        )
        await session.execute(upsert_statement, inserted_aliases)
