import asyncio
import contextlib
import functools
import logging
import logging.handlers
import sys
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Optional

import discord
import sqlalchemy.event
from aiohttp import web
from discord.ext import commands
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cogs import COG_LIST
from database.models import Prefix
from utils.config import config
from utils.evtloop import get_event_loop
from utils.help import HelpCommand
from utils.logging import QueueListenerHandler, console_handler, logger, setup_handler
from web import init_app

if TYPE_CHECKING:
    from aiohttp.web import Application
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


BOT_DIR = Path(__file__).parent


class ChuniBot(commands.Bot):
    dev: bool = False

    engine: "AsyncEngine"
    begin_db_session: async_sessionmaker["AsyncSession"]

    launch_time: float
    app: Optional["Application"] = None

    # Prefix cache
    prefixes: dict[int, str]

    # key: user discord ID
    # value: userId, _t cookies from CHUNITHM-NET
    sessions: dict[int, tuple[str | None, str | None]]

    def __init__(self, *args, **kwargs):
        self.dev = config.dangerous.dev
        self.prefixes = {}
        self.sessions = {}

        super().__init__(*args, **kwargs)

    async def start(self, *args, **kwargs):
        self.launch_time = time()
        return await super().start(*args, **kwargs)

    async def setup_hook(self) -> None:
        # Database setup
        connection_string = config.bot.db_connection_string
        self.engine = create_async_engine(connection_string)
        self.begin_db_session = async_sessionmaker(self.engine, expire_on_commit=False)

        def setup_database(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.create_function(
                "fuzz_qratio",
                2,
                functools.partial(fuzz.QRatio, processor=str.lower),  # type: ignore[reportCallIssue]
            )

        sqlalchemy.event.listen(self.engine.sync_engine, "connect", setup_database)

        # Load guild prefixes
        async with self.begin_db_session() as session:
            prefixes = (await session.execute(select(Prefix))).scalars()

        self.prefixes = {prefix.guild_id: prefix.prefix for prefix in prefixes}
        logger.info(f"Loaded {len(self.prefixes)} guild prefixes")

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
                )
            )

        if self.dev:
            await self.load_extension("cogs.hotreload")
            await self.load_extension("jishaku")

        for cog in COG_LIST:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension {cog}")
            except commands.errors.ExtensionAlreadyLoaded:  # noqa: PERF203
                logger.warning(f"{cog} already loaded")
            except commands.errors.NoEntryPointError:
                logger.error(f"{COG_LIST} has no `setup` function.")
            except commands.errors.ExtensionFailed as e:
                logger.error(
                    f"{cog} raised an error: {e.original.__class__.__name__}: {e.original}"
                )

    async def close(self) -> None:
        if self.app is not None:
            await self.app.shutdown()
            await self.app.cleanup()

        if hasattr(self, "engine"):
            await self.engine.dispose()

        return await super().close()


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

    (intents := discord.Intents.default()).message_content = True
    bot = ChuniBot(
        command_prefix=guild_specific_prefix(config.bot.default_prefix),  # type: ignore[reportGeneralTypeIssues]
        intents=intents,
        help_command=HelpCommand(),
        config=config,
    )

    discord.utils.setup_logging(
        level=logging.DEBUG if bot.dev else logging.INFO,
        handler=QueueListenerHandler(
            console_handler,
            setup_handler(
                logging.handlers.RotatingFileHandler(
                    filename="discord.log",
                    encoding="utf-8",
                    maxBytes=32 * 1024 * 1024,  # 32 MiB
                    backupCount=5,  # Rotate through 5 files
                ),
            ),
        ),
        root=False,
    )

    try:
        async with bot:
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
