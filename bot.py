import asyncio
import contextlib
import functools
import signal
import sqlite3
import sys
import time
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Optional, cast

import discord
import discord.utils
import sqlalchemy.event
from aiohttp import web
from discord.ext import commands
from rapidfuzz import fuzz
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cogs import COG_LIST
from cogs.gaming.states.base import GuessingGameSkippableState
from database.models import Prefix
from utils import json_dumps, json_loads
from utils.command_tree import VersionableCommandTree
from utils.config import config
from utils.evtloop import get_event_loop
from utils.help import HelpCommand
from utils.logging import logger
from web import init_app

if TYPE_CHECKING:
    from aiohttp.web import Application
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from cogs.gaming import GamingCog


BOT_DIR = Path(__file__).parent


discord.utils._from_json = json_loads
discord.utils._to_json = json_dumps


class KeyboardInterruptHandler:
    def __init__(self, bot: "ChuniBot"):
        self.bot: "ChuniBot" = bot
        self._pending: bool = False

    def __call__(
        self,
        signal: int | None = None,
        frame: FrameType | None = None,
    ):
        if self._pending:
            raise KeyboardInterrupt

        self.bot.loop.call_soon_threadsafe(
            self.bot.loop.create_task,
            self.bot.close(),
        )
        self.bot.loop.call_soon_threadsafe(
            lambda: None
        )  # no-op to wake up loop (important!)
        self._pending = True


class ChuniBot(commands.AutoShardedBot):
    dev: bool = False

    engine: "AsyncEngine"
    begin_db_session: async_sessionmaker["AsyncSession"]

    launch_time: float
    app: Optional["Application"] = None

    # Prefix cache
    prefixes: dict[int, str]

    command_start_time: dict[commands.Context, int]

    def __init__(self):
        intents = discord.Intents(
            guilds=True,
            voice_states=True,
            messages=True,
            typing=True,
            message_content=True,
        )

        command_prefix = guild_specific_prefix(config.bot.default_prefix)
        help_command = HelpCommand()

        super().__init__(
            command_prefix=command_prefix,
            help_command=help_command,
            intents=intents,
            tree_cls=VersionableCommandTree,
        )

        self.dev = config.dangerous.dev
        self.prefixes = {}
        self.command_start_time = {}

    async def start(self, *args, **kwargs):
        self.launch_time = time.time()
        return await super().start(*args, **kwargs)

    async def setup_hook(self) -> None:
        # Database setup
        connection_string = config.bot.db_connection_string
        self.engine = create_async_engine(connection_string)
        self.begin_db_session = async_sessionmaker(self.engine, expire_on_commit=False)

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

            cursor = conn.cursor()

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

            cursor.close()

        # Load guild prefixes
        async with self.begin_db_session() as session:
            prefixes = (await session.execute(select(Prefix))).scalars()

        self.prefixes = {prefix.guild_id: prefix.prefix for prefix in prefixes}
        await logger.ainfo(
            "Loaded guild prefixes",
            tag="load_guild_prefix",
            prefix_count=len(self.prefixes),
        )

        # Setup login web server (if enabled)
        if config.web.enable:
            self.app = init_app(
                self,
                goatcounter=config.web.goatcounter,
                base_url=config.web.base_url,
                kamaitachi_client_id=config.credentials.kamaitachi_client_id,
                kamaitachi_client_secret=config.credentials.kamaitachi_client_secret,
            )
            _ = asyncio.ensure_future(  # noqa: RUF006
                web._run_app(
                    self.app,
                    port=config.web.port,
                    host=config.web.listen_address,
                    handle_signals=False,
                )
            )

        if self.dev:
            await self.load_extension("jishaku")

        for cog in COG_LIST:
            try:
                await self.load_extension(cog)
                await logger.ainfo(
                    "Loaded extension",
                    tag="load_extension",
                    extension=cog,
                )
            except commands.errors.ExtensionAlreadyLoaded:
                await logger.awarning(
                    "Extension already loaded",
                    tag="extension_already_loaded",
                    extension=cog,
                )
                logger.warning(f"{cog} already loaded")
            except commands.errors.NoEntryPointError:
                await logger.aerror(
                    "Extension has no `setup` function.",
                    tag="extension_missing_entry_point",
                    extension=cog,
                )
            except commands.errors.ExtensionFailed as e:
                await logger.exception(
                    "Extension raised error",
                    tag="extension_error",
                    extension=cog,
                    exc_info=e,
                )

        tree = cast(VersionableCommandTree, self.tree)
        current_tree_hash = await tree.get_hash()

        # very much an abuse but i can't be asked to add yet another database table
        # nor use a temp file since i have to parse string back to number
        async with self.begin_db_session() as session:
            result = await session.execute(text("PRAGMA user_version"))
            old_tree_hash: int | None = result.scalar_one_or_none()

            if old_tree_hash != current_tree_hash:
                await logger.ainfo(
                    "Command tree updated",
                    tag="command_tree_updated",
                    old_hash=old_tree_hash,
                    new_hash=current_tree_hash,
                )
                await self.tree.sync()
                await session.execute(text(f"PRAGMA user_version={current_tree_hash}"))

    async def _close_web(self):
        if self.app is not None:
            await self.app.shutdown()
            await self.app.cleanup()

    async def _close_database(self):
        async with self.begin_db_session() as session:
            await session.execute(text("PRAGMA optimize"))

        await self.engine.dispose()

    async def _close_games(self):
        gaming = cast("GamingCog | None", self.get_cog("Games"))

        if gaming is not None:
            gaming.shutting_down = True

            warning_embed = discord.Embed(
                color=discord.Color.yellow(),
                title="Warning",
                description="I'll be going down for an update soon. Please finish your game in five minutes.",
            )

            async with gaming.game_sessions_lock:
                await asyncio.gather(
                    *[
                        s.channel.send(embed=warning_embed)
                        for s in gaming.game_sessions.values()
                    ]
                )

            if len(gaming.game_tasks) > 0:
                _, pending = await asyncio.wait(gaming.game_tasks, timeout=300)
            else:
                pending = set()

            async with gaming.game_sessions_lock:
                for session in gaming.game_sessions.values():
                    session.stopped_by = self.user

            async with gaming.state_for_game_session_lock:
                for state in gaming.state_for_game_session.values():
                    if isinstance(state, GuessingGameSkippableState):
                        await state.skip()

            if len(pending) > 0:
                await asyncio.wait(pending)

    async def close(self) -> None:
        await self._close_games()

        await asyncio.gather(
            self._close_web(),
            self._close_database(),
            return_exceptions=True,
        )

        await super().close()


def guild_specific_prefix(default: str):
    async def inner(bot: ChuniBot, msg: discord.Message) -> list[str]:
        when_mentioned = commands.when_mentioned(bot, msg)

        if msg.guild is None:
            return [*when_mentioned, default]

        return [*when_mentioned, bot.prefixes.get(msg.guild.id, default)]

    return inner


async def startup():
    if (token := config.bot.token) is None:
        logger.error("Token not found. Make sure 'bot.token' is set in 'bot.ini'.")
        sys.exit(1)

    try:
        async with ChuniBot() as bot:
            handler = KeyboardInterruptHandler(bot)

            try:
                bot.loop.add_signal_handler(signal.SIGINT, handler)
                bot.loop.add_signal_handler(signal.SIGTERM, handler)
            except NotImplementedError:  # fucking windows
                signal.signal(signal.SIGINT, handler)
                signal.signal(signal.SIGTERM, handler)

            await bot.start(token, reconnect=True)
    except discord.LoginFailure:
        logger.error(
            "Invalid token. Make sure 'bot.token' is properly set in 'bot.ini'."
        )
        sys.exit(1)
    except discord.PrivilegedIntentsRequired:
        logger.error(
            "Message Content Intent not enabled, go to 'https://discord.com/developers/applications' and enable the Message Content Intent."
        )
        sys.exit(1)


def sync_startup():
    event_loop_impl, loop_factory = get_event_loop()

    if sys.version_info >= (3, 11):
        with asyncio.Runner(loop_factory=loop_factory) as runner:
            runner.run(startup())
    else:
        if event_loop_impl is not None:
            event_loop_impl.install()
        asyncio.run(startup())


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sync_startup()
