from pathlib import Path

from dotenv import dotenv_values

BOT_DIR = Path(__file__).absolute().parent
cfg = dotenv_values(BOT_DIR / ".env")


import asyncio
import logging
import logging.handlers
import sys
from time import time
from typing import TYPE_CHECKING, Optional

import discord
import sqlalchemy.event
from aiohttp import web
from discord.ext import commands
from discord.ext.commands import Bot
from jarowinkler import jarowinkler_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from database.models import Base, Prefix
from utils.help import HelpCommand
from web import init_app

if TYPE_CHECKING:
    from aiohttp.web import Application


class ChuniBot(Bot):
    cfg: dict[str, str | None]
    dev: bool = False

    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///" + str(BOT_DIR / "database" / "database.sqlite3")
    )
    begin_db_session: async_sessionmaker[AsyncSession]

    launch_time: float
    app: Optional["Application"] = None

    prefixes: dict[int, str]

    # key: user discord ID
    # value: userId, _t cookies from CHUNITHM-NET
    sessions: dict[int, tuple[str | None, str | None]] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.begin_db_session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def setup_hook(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.begin_db_session() as session:
            prefixes = (await session.execute(select(Prefix))).scalars()

        self.prefixes = {prefix.guild_id: prefix.prefix for prefix in prefixes}


def guild_specific_prefix(default: str):
    async def inner(bot: ChuniBot, msg: discord.Message) -> list[str]:
        when_mentioned = commands.when_mentioned(bot, msg)

        if msg.guild is None:
            return when_mentioned + [default]
        else:
            return when_mentioned + [bot.prefixes.get(msg.guild.id, default)]

    return inner


def setup_database(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.create_function("jwsim", 2, jarowinkler_similarity)


async def startup():
    if (token := cfg.get("TOKEN")) is None:
        sys.exit(
            "[ERROR] Token not found, make sure 'TOKEN' is set in the '.env' file. Exiting."
        )

    (intents := discord.Intents.default()).message_content = True
    bot = ChuniBot(
        command_prefix=guild_specific_prefix(cfg.get("DEFAULT_PREFIX", "c>")),  # type: ignore
        intents=intents,
        help_command=HelpCommand(),
    )
    bot.cfg = cfg
    bot.dev = cfg.get("DEV", "0") == "1"

    handler = logging.handlers.RotatingFileHandler(
        filename="discord.log",
        encoding="utf-8",
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,  # Rotate through 5 files
    )
    dt_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
    )

    discord.utils.setup_logging(
        handler=handler,
        formatter=formatter,
        level=logging.DEBUG if bot.dev else logging.INFO,
        root=False,
    )

    await bot.load_extension("cogs.botutils")
    if bot.dev:
        await bot.load_extension("cogs.hotreload")
        await bot.load_extension("jishaku")

    for file in (BOT_DIR / "cogs").glob("*.py"):
        if file.stem in ["hotreload", "botutils", "__init__"]:
            continue
        try:
            await bot.load_extension(f"cogs.{file.stem}")
            print(f"Loaded cogs.{file.stem}")
        except Exception as e:
            print(f"Failed to load extension cogs.{file.stem}")
            print(f"{type(e).__name__}: {e}")

    sqlalchemy.event.listen(bot.engine.sync_engine, "connect", setup_database)

    port = cfg.get("LOGIN_ENDPOINT_PORT", "5730")
    if port is not None and port.isdigit() and int(port) > 0:
        bot.app = init_app(bot)
        asyncio.ensure_future(
            web._run_app(
                bot.app,
                port=int(port),
                host="127.0.0.1",
            )
        )

    try:
        bot.launch_time = time()
        await bot.start(token)
    except discord.LoginFailure:
        sys.exit(
            "[ERROR] Token not found, make sure 'TOKEN' is set in the '.env' file. Exiting."
        )
    except discord.PrivilegedIntentsRequired:
        sys.exit(
            "[ERROR] Message Content Intent not enabled, go to 'https://discord.com/developers/applications' and enable the Message Content Intent. Exiting."
        )


if __name__ == "__main__":
    asyncio.run(startup())
