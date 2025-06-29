import contextlib
import functools
import sqlite3
from typing import TYPE_CHECKING, override

import sqlalchemy.event
from discord.ext import commands, tasks
from rapidfuzz import fuzz
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from utils.config import config

if TYPE_CHECKING:
    from bot import ChuniBot


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

        # Wait until database isn't locked any more for 100ms before throwing "Database is busy" errors.
        cursor.execute("PRAGMA busy_timeout=100")

        # Enables query planner optimization.
        cursor.execute("PRAGMA optimize=0x10002")

        # Enables recursive triggers.
        cursor.execute("PRAGMA recursive_triggers=ON")


class DatabaseCog(commands.Cog, name="Database"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

        self._engine: AsyncEngine = create_async_engine(config.bot.db_connection_string)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

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

    @tasks.loop(hours=1)
    async def optimize_database(self):
        async with self.bot.begin_db_session() as session:
            await session.execute(text("PRAGMA optimize"))


async def setup(bot: "ChuniBot"):
    await bot.add_cog(DatabaseCog(bot))
