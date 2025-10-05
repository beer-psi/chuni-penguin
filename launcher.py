# ruff: noqa: E402
from chuni_penguin.utils import monkey

monkey.patch_all()

import asyncio
import contextlib
import signal
import sys
from types import FrameType

import discord

from chuni_penguin.bot import ChuniBot
from chuni_penguin.config import config
from chuni_penguin.logging import logger
from chuni_penguin.utils import get_loop_factory


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


if __name__ == "__main__":
    with (
        contextlib.suppress(KeyboardInterrupt),
        asyncio.Runner(loop_factory=get_loop_factory()) as runner,
    ):
        runner.run(startup())
