import asyncio
import contextlib
import sqlite3
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, overload, override

import msgspec
import sqlalchemy
import sqlalchemy.event
import sqlalchemy.util
from discord.ext import commands, tasks
from discord.utils import MISSING
from sqlalchemy import Executable, Result, case, delete, func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.sql.selectable import TypedReturnsRows

from chuni_penguin.config import config
from chuni_penguin.database import (
    Chart,
    Cookie,
    EasterEggFound,
    PendingKamaitachiImport,
    PersonalBest,
    Song,
)
from chuni_penguin.networks.consts import KEY_SONG_ID
from chuni_penguin.networks.kamaitachi import KTBatchManualChunithm
from chuni_penguin.networks.types import Difficulty, RecentScore, Score

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


def setup_database(conn: AsyncAdapt_aiosqlite_connection, _):
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

        # Wait until database isn't locked any more for 10000ms before throwing "Database is busy" errors.
        cursor.execute("PRAGMA busy_timeout=10000")

        # Enables query planner optimization.
        cursor.execute("PRAGMA optimize=0x10002")

        # Enables recursive triggers.
        cursor.execute("PRAGMA recursive_triggers=ON")

        # Increase the cache size to 51200 KiB = 50 MiB.
        cursor.execute("PRAGMA cache_size=-51200")

        # Increase memory-mapped I/O size to 50 MiB, which should be more than enough
        # for the current database (production is around 10MB).
        cursor.execute("PRAGMA mmap_size=52428800")

        # Store temporary tables and indices in memory.
        cursor.execute("PRAGMA temp_store=MEMORY")


def disable_isolation_level(conn: AsyncAdapt_aiosqlite_connection, _):
    conn.isolation_level = None


def emit_begin_immediate(conn: sqlalchemy.Connection):
    conn.exec_driver_sql("BEGIN IMMEDIATE")


class WriteTask[T]:
    __slots__ = ("fn", "future", "transaction")

    def __init__(
        self,
        fn: Callable[[AsyncSession], Awaitable[T]],
        future: asyncio.Future[T],
        *,
        transaction: bool = True,
    ):
        self.fn = fn
        self.future = future
        self.transaction = transaction


def safe_set_result[T](future: asyncio.Future[T], result: T):
    if not future.done():
        future.set_result(result)


def safe_set_exception(future: asyncio.Future, exception: Exception):
    if not future.done():
        future.set_exception(exception)


class WriterQueue:
    __slots__ = (
        "_engine",
        "_loop",
        "_queue",
        "_sessionmaker",
        "_stop_event",
        "_writer_task",
    )

    def __init__(
        self, engine: AsyncEngine, *, loop: asyncio.AbstractEventLoop | None = None
    ):
        self._engine = engine
        self._loop = loop or asyncio.get_event_loop()
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self._queue: asyncio.Queue[WriteTask] = asyncio.Queue()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._writer_task: asyncio.Task | None = None

    def start(self):
        self._writer_task = asyncio.create_task(self.task())

    async def task(self):
        while not self._stop_event.is_set():
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            else:
                if task.future.done():  # weird, but okay
                    return

                try:
                    if task.transaction:
                        async with self._sessionmaker() as session, session.begin():
                            result = await task.fn(session)
                    else:
                        async with self._sessionmaker() as session:
                            result = await task.fn(session)
                except Exception as e:  # noqa: BLE001
                    task.future.get_loop().call_soon_threadsafe(
                        safe_set_exception, task.future, e
                    )
                else:
                    task.future.get_loop().call_soon_threadsafe(
                        safe_set_result, task.future, result
                    )

    def stop(self):
        self._stop_event.set()

    @overload
    async def execute[T: Any](
        self,
        statement: TypedReturnsRows[T],
        params: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = ...,
        *,
        execution_options: Mapping[str, Any] = ...,
        bind_arguments: dict[str, Any] | None = ...,
        transaction: bool = ...,
    ) -> Result[T]: ...

    @overload
    async def execute(
        self,
        statement: Executable,
        params: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = ...,
        *,
        execution_options: Mapping[str, Any] = ...,
        bind_arguments: dict[str, Any] | None = ...,
        transaction: bool = ...,
    ) -> Result[Any]: ...

    async def execute(
        self,
        statement: Executable,
        params: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
        *,
        execution_options: Mapping[str, Any] = sqlalchemy.util.EMPTY_DICT,
        bind_arguments: dict[str, Any] | None = None,
        transaction: bool = True,
    ) -> Result[Any]:
        return await self.execute_fn(
            lambda session: session.execute(
                statement,
                params,
                execution_options=execution_options,
                bind_arguments=bind_arguments,
            ),
            transaction=transaction,
        )

    async def merge[T: object](
        self,
        instance: T,
        *,
        load: bool = True,
        options: Sequence[ORMOption] | None = None,
        transaction: bool = True,
    ) -> T:
        return await self.execute_fn(
            lambda session: session.merge(instance, load=load, options=options),
            transaction=transaction,
        )

    async def add(self, instance: object, *, transaction: bool = True):
        async def inner(session: AsyncSession):
            session.add(instance)

        return await self.execute_fn(inner, transaction=transaction)

    async def delete(self, instance: object, *, transaction: bool = True):
        return await self.execute_fn(
            lambda session: session.delete(instance), transaction=transaction
        )

    def execute_fn[T](
        self, fn: Callable[[AsyncSession], Awaitable[T]], *, transaction: bool = True
    ) -> asyncio.Future[T]:
        future: asyncio.Future[T] = self._loop.create_future()
        entry = WriteTask(fn, future, transaction=transaction)

        self._queue.put_nowait(entry)

        return future


class CookieQueries:
    __slots__ = ("_read_sessionmaker", "_writer")

    def __init__(
        self,
        writer: WriterQueue,
        read_sessionmaker: async_sessionmaker[AsyncSession],
    ):
        self._writer = writer
        self._read_sessionmaker = read_sessionmaker

    async def get_by_discord_id(self, discord_id: int):
        async with self._read_sessionmaker() as session:
            query = select(Cookie).where(Cookie.discord_id == discord_id)
            return (await session.execute(query)).scalar_one_or_none()

    async def set_friend_code(self, discord_id: int, friend_code: str):
        query = insert(Cookie).values(
            discord_id=discord_id,
            cookie="",
            kamaitachi_token=None,
            friend_code=friend_code,
            is_contributor=False,
            is_supporter=False,
        )
        query = query.on_conflict_do_update(
            index_elements=[Cookie.discord_id],
            set_={"friend_code": query.excluded.friend_code},
        )

        await self._writer.execute(query)


class SongQueries:
    __slots__ = ("_read_sessionmaker", "_writer")

    def __init__(
        self,
        writer: WriterQueue,
        read_sessionmaker: async_sessionmaker[AsyncSession],
    ):
        self._writer = writer
        self._read_sessionmaker = read_sessionmaker

    async def get_hidden_on_chuninet(self):
        async with self._read_sessionmaker() as session:
            query = select(Song).where(
                (Song.is_hidden_on_chuninet == True) & (Song.available == True)  # noqa: E712
            )
            return (await session.execute(query)).scalars().all()


class ChartQueries:
    __slots__ = ("_read_sessionmaker", "_writer")

    def __init__(
        self,
        writer: WriterQueue,
        read_sessionmaker: async_sessionmaker[AsyncSession],
    ):
        self._writer = writer
        self._read_sessionmaker = read_sessionmaker

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

        async with self._read_sessionmaker() as session:
            return (await session.execute(query)).scalars().all()


class PendingKamaitachiImportQueries:
    __slots__ = ("_read_sessionmaker", "_writer")

    def __init__(
        self,
        writer: WriterQueue,
        read_sessionmaker: async_sessionmaker[AsyncSession],
    ):
        self._writer = writer
        self._read_sessionmaker = read_sessionmaker

    async def insert(self, discord_id: int, import_data: dict[str, Any]):
        await self._writer.execute(
            insert(PendingKamaitachiImport).values(
                discord_id=discord_id, import_data=import_data
            )
        )

    async def get_import_data(self, discord_id: int):
        async with self._read_sessionmaker() as session:
            query = select(PendingKamaitachiImport).where(
                PendingKamaitachiImport.discord_id == discord_id
            )
            data = (await session.execute(query)).scalars().all()

        # Fast path optimizations
        if len(data) == 1:
            return msgspec.convert(data[0].import_data, type=KTBatchManualChunithm)

        import_data = KTBatchManualChunithm()

        # this should probably never happen but just in case
        if len(data) == 0:
            return import_data

        for datum in data:
            datum_import = msgspec.convert(
                datum.import_data, type=KTBatchManualChunithm
            )
            import_data.scores += datum_import.scores

            if datum_import.classes.dan is not msgspec.UNSET:
                if import_data.classes.dan is not msgspec.UNSET:
                    import_data.classes.dan = max(
                        datum_import.classes.dan, import_data.classes.dan
                    )
                else:
                    import_data.classes.dan = datum_import.classes.dan

            if datum_import.classes.emblem is not msgspec.UNSET:
                if import_data.classes.emblem is not msgspec.UNSET:
                    import_data.classes.emblem = max(
                        datum_import.classes.emblem, import_data.classes.emblem
                    )
                else:
                    import_data.classes.emblem = datum_import.classes.emblem

        return import_data

    async def delete_all(self, discord_id: int):
        query = delete(PendingKamaitachiImport).where(
            PendingKamaitachiImport.discord_id == discord_id
        )
        await self._writer.execute(query)


class PersonalBestQueries:
    __slots__ = ("_read_sessionmaker", "_writer")

    def __init__(
        self,
        writer: WriterQueue,
        read_sessionmaker: async_sessionmaker[AsyncSession],
    ):
        self._writer = writer
        self._read_sessionmaker = read_sessionmaker

    async def upsert_personal_bests(
        self, discord_id: int, network: str, scores: Sequence[Score]
    ) -> Sequence[PersonalBest]:
        if not scores:
            return []

        query = insert(PersonalBest)
        conflict_sets: dict[str, Any] = {
            "score": func.max(PersonalBest.score, query.excluded.score),
            "clear_lamp": func.max(PersonalBest.clear_lamp, query.excluded.clear_lamp),
            "combo_lamp": func.max(PersonalBest.combo_lamp, query.excluded.combo_lamp),
            "achieved_at": case(
                (
                    (
                        (query.excluded.score > PersonalBest.score)
                        | (query.excluded.clear_lamp > PersonalBest.clear_lamp)
                        | (query.excluded.combo_lamp > PersonalBest.combo_lamp)
                    )
                    & query.excluded.achieved_at.is_not(None)
                    & PersonalBest.achieved_at.is_not(None),
                    func.max(query.excluded.achieved_at, PersonalBest.achieved_at),
                ),
                (
                    (query.excluded.score > PersonalBest.score)
                    | (query.excluded.clear_lamp > PersonalBest.clear_lamp)
                    | (query.excluded.combo_lamp > PersonalBest.combo_lamp),
                    query.excluded.achieved_at,
                ),
                (
                    (query.excluded.score == PersonalBest.score)
                    & (query.excluded.clear_lamp == PersonalBest.clear_lamp)
                    & (query.excluded.combo_lamp == PersonalBest.combo_lamp)
                    & PersonalBest.achieved_at.is_(None),
                    query.excluded.achieved_at,
                ),
                else_=PersonalBest.achieved_at,
            ),
        }

        # Merge nullable columns by their max values. This whole case block is needed
        # since MAX(x, NULL) -> NULL, at least in SQLite.
        for column_name in ("chain_lamp", "last_played_at"):
            column = getattr(PersonalBest, column_name)
            excluded_column = getattr(query.excluded, column_name)

            conflict_sets[column_name] = case(
                (
                    column.is_(None) & excluded_column.is_not(None),
                    excluded_column,
                ),
                (
                    column.is_not(None) & excluded_column.is_(None),
                    column,
                ),
                # At this point, either both values are null, and MAX(NULL, NULL) -> NULL
                # or both values are not null and we get an actual max value.
                else_=func.max(column, excluded_column),
            )

        # Merge score dependent columns based on the score. In case of ties, we select
        # the score already in the database.
        for column in (
            "justice_heaven",
            "justice_critical",
            "justice",
            "attack",
            "miss",
            "max_combo",
        ):
            conflict_sets[column] = case(
                (
                    query.excluded.score > PersonalBest.score,
                    getattr(query.excluded, column),
                ),
                (
                    (query.excluded.score == PersonalBest.score)
                    & (getattr(PersonalBest, column).is_(None)),
                    getattr(query.excluded, column),
                ),
                else_=getattr(PersonalBest, column),
            )

        query = query.on_conflict_do_update(
            index_elements=[
                PersonalBest.discord_id,
                PersonalBest.network,
                PersonalBest.song_id,
                PersonalBest.difficulty,
            ],
            set_=conflict_sets,
        )

        params: list[dict[str, Any]] = []

        for score in scores:
            if KEY_SONG_ID not in score.extras:
                continue

            param = {
                "discord_id": discord_id,
                "network": network,
                "song_id": score.extras[KEY_SONG_ID],
                "difficulty": score.difficulty.short(),
                "score": score.score,
                "max_combo": score.max_combo,
                "clear_lamp": score.clear_lamp.value,
                "combo_lamp": score.combo_lamp.value,
                "chain_lamp": (
                    score.chain_lamp.value if score.chain_lamp is not None else None
                ),
                "achieved_at": score.achieved_at,
                "last_played_at": (
                    score.achieved_at if isinstance(score, RecentScore) else None
                ),
            }

            if score.judgements is not None:
                param["justice_heaven"] = score.judgements.justice_heaven
                param["justice_critical"] = score.judgements.justice_critical
                param["justice"] = score.judgements.justice
                param["attack"] = score.judgements.attack
                param["miss"] = score.judgements.miss

            params.append(param)

        result = await self._writer.execute(query.returning(PersonalBest))

        return result.scalars().all()


class DatabaseCog(commands.Cog, name="Database"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

        self._readwrite_engine: AsyncEngine = create_async_engine(
            config.bot.db_connection_string,
            hide_parameters=not config.dangerous.dev,
            pool_size=1,
            max_overflow=0,
        )

        sqlalchemy.event.listens_for(self._readwrite_engine.sync_engine, "connect")(
            setup_database
        )
        sqlalchemy.event.listens_for(self._readwrite_engine.sync_engine, "connect")(
            disable_isolation_level
        )
        sqlalchemy.event.listens_for(self._readwrite_engine.sync_engine, "begin")(
            emit_begin_immediate
        )

        self.writer: WriterQueue = MISSING

        self._read_engine: AsyncEngine = create_async_engine(
            config.bot.db_connection_string + "?mode=ro",
            hide_parameters=not config.dangerous.dev,
            pool_size=10,
        )

        sqlalchemy.event.listens_for(self._read_engine.sync_engine, "connect")(
            setup_database
        )

        self._read_sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._read_engine, expire_on_commit=False
        )

        self.cookies: CookieQueries = MISSING
        self.songs: SongQueries = MISSING
        self.charts: ChartQueries = MISSING
        self.pending_kamaitachi_imports: PendingKamaitachiImportQueries = MISSING
        self.personal_bests: PersonalBestQueries = MISSING

    @override
    async def cog_load(self) -> None:
        self.writer = WriterQueue(self._readwrite_engine, loop=self.bot.loop)
        self.writer.start()

        self.cookies = CookieQueries(self.writer, self._read_sessionmaker)
        self.songs = SongQueries(self.writer, self._read_sessionmaker)
        self.charts = ChartQueries(self.writer, self._read_sessionmaker)
        self.pending_kamaitachi_imports = PendingKamaitachiImportQueries(
            self.writer, self._read_sessionmaker
        )
        self.personal_bests = PersonalBestQueries(self.writer, self._read_sessionmaker)

        self._optimize_database.start()

    @override
    async def cog_unload(self) -> None:
        self._optimize_database.stop()

        await self.writer.execute(text("PRAGMA optimize"), transaction=False)
        self.writer.stop()

        await self._read_engine.dispose()
        await self._readwrite_engine.dispose()

    @property
    def readwrite_engine(self):
        return self._readwrite_engine

    @property
    def read_engine(self):
        return self._read_engine

    @property
    def read_sessionmaker(self):
        return self._read_sessionmaker

    @tasks.loop(hours=1, reconnect=True)
    async def _optimize_database(self):
        await self.writer.execute(text("PRAGMA optimize"), transaction=False)

    async def user_found_easter_egg(self, user_id: int, easter_egg: str):
        await self.writer.execute(
            insert(EasterEggFound)
            .values(discord_id=user_id, easter_egg=easter_egg)
            .on_conflict_do_nothing()
        )

    async def count_easter_eggs_found(self, user_id: int):
        async with self._read_sessionmaker() as session:
            result = await session.execute(
                select(func.count()).where(EasterEggFound.discord_id == user_id)
            )
            return result.scalar_one()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(DatabaseCog(bot))
