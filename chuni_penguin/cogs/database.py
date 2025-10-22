import contextlib
import functools
import sqlite3
from typing import TYPE_CHECKING, override

import sqlalchemy.event
from discord.ext import commands, tasks
from rapidfuzz import fuzz
from sqlalchemy import func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chuni_penguin.config import config
from chuni_penguin.database import Chart, EasterEggFound, Song
from chuni_penguin.networks.types import Difficulty

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


@sqlalchemy.event.listens_for(Engine, "connect")
def setup_database(conn: AsyncAdapt_aiosqlite_connection, _):
    conn.create_function(
        "fuzz_qratio",
        2,
        functools.partial(fuzz.QRatio, processor=str.lower),  # type: ignore[reportCallIssue]
    )

    # Disable allowing double quotes on strings
    conn._connection._connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, 0)
    conn._connection._connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, 0)

    with contextlib.closing(conn.cursor()) as cursor:
        # Turns on write-ahead logging: https://www.sqlite.org/wal.html
        cursor.execute("PRAGMA journal_mode=WAL")

        # Sychronize to disk less offten for performance boosts. WAL mode is safe
        # from corruption even in this mode.
        cursor.execute("PRAGMA synchronous=NORMAL")

        # Foreign keys need to be enabled to have an effect. https://www.sqlite.org/foreignkeys.html#fk_enable
        cursor.execute("PRAGMA foreign_keys=ON")

        # Wait until database isn't locked any more for 5000ms before throwing "Database is busy" errors.
        cursor.execute("PRAGMA busy_timeout=5000")

        # Enables query planner optimization.
        cursor.execute("PRAGMA optimize=0x10002")

        # Enables recursive triggers.
        cursor.execute("PRAGMA recursive_triggers=ON")


class SongQueries:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    async def get_hidden_on_chuninet(self):
        async with self._sessionmaker() as session:
            query = select(Song).where(
                (Song.is_hidden_on_chuninet == True) & (Song.available == True)  # noqa: E712
            )
            return (await session.execute(query)).scalars().all()


class ChartQueries:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    async def get_hidden_on_chuninet(
        self, level: str | None = None, difficulty: Difficulty | None = None
    ):
        query = (
            select(Chart)
            .join(Song, Chart.song_id == Song.id)
            .where((Song.is_hidden_on_chuninet == True) & (Song.available == True))  # noqa: E712
        )

        if level is not None:
            query = query.where(Chart.level == level)

        if difficulty is not None:
            query = query.where(Chart.difficulty == difficulty.short())

        async with self._sessionmaker() as session:
            return (await session.execute(query)).scalars().all()


class DatabaseCog(commands.Cog, name="Database"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

        self._engine: AsyncEngine = create_async_engine(
            config.bot.db_connection_string, hide_parameters=True
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

        self.songs = SongQueries(self._sessionmaker)
        self.charts = ChartQueries(self._sessionmaker)

    @override
    async def cog_load(self) -> None:
        self.optimize_database.start()

    @override
    async def cog_unload(self) -> None:
        self.optimize_database.stop()

        async with self._sessionmaker() as session:
            await session.execute(text("PRAGMA optimize"))

        await self._engine.dispose()

    @property
    def engine(self):
        return self._engine

    @property
    def sessionmaker(self):
        return self._sessionmaker

    @tasks.loop(hours=1, reconnect=True)
    async def optimize_database(self):
        async with self.bot.begin_db_session() as session:
            await session.execute(text("PRAGMA optimize"))

    async def user_found_easter_egg(self, user_id: int, easter_egg: str):
        async with self._sessionmaker() as session:
            query = (
                insert(EasterEggFound)
                .values(discord_id=user_id, easter_egg=easter_egg)
                .on_conflict_do_nothing()
            )
            await session.execute(query)
            await session.commit()

    async def count_easter_eggs_found(self, user_id: int):
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(func.count()).where(EasterEggFound.discord_id == user_id)
            )
            return result.scalar_one()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(DatabaseCog(bot))
