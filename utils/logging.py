import functools
import logging
import time
from logging import LogRecord
from typing import TYPE_CHECKING, Any, override

import structlog
from structlog.stdlib import BoundLogger

from utils.config import config

if TYPE_CHECKING:
    from discord import Interaction
    from discord.app_commands.commands import CommandCallback as AppCommandCallback
    from discord.app_commands.commands import GroupT
    from discord.ext.commands._types import ContextT
    from discord.ext.commands.hybrid import CogT, CommandCallback, P, T

__all__ = ("logged_app_command", "logged_prefix_command", "logger")


processors = structlog.get_config()["processors"][:-1]

if config.dangerous.dev:
    processors.append(structlog.dev.ConsoleRenderer())
else:
    processors.append(structlog.processors.dict_tracebacks)
    processors.append(structlog.processors.JSONRenderer())

structlog.configure(processors=processors)
logger: BoundLogger = structlog.get_logger()


class StructlogHandler(logging.Handler):
    def __init__(self, level: int = 0) -> None:
        super().__init__(level)
        self._logger: BoundLogger = structlog.get_logger()

    @override
    def emit(self, record: LogRecord) -> None:
        self._logger.log(record.levelno, record.getMessage(), logger=record.name)


def logged_prefix_command(coro: "CommandCallback[CogT, ContextT, P, T]"):
    @functools.wraps(coro)  # pyright: ignore[reportArgumentType]
    async def callback(self: "CogT", ctx: "ContextT", *args, **kwargs):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            execution_id=ctx.message.id,
            command_name=ctx.command.qualified_name if ctx.command else None,
            is_app_command=ctx.interaction is not None,
        )

        command_failed = False
        start_time_ns = time.perf_counter_ns()

        try:
            return await coro(self, ctx, *args, **kwargs)  # pyright: ignore[reportCallIssue]
        except Exception:
            command_failed = True
            raise
        finally:
            end_time_ns = time.perf_counter_ns()
            duration = (end_time_ns - start_time_ns) // 1_000_000
            _log = logger.aerror if command_failed else logger.ainfo

            await _log(
                "Command finished execution",
                tag="command_finished",
                invoked_with=ctx.invoked_with,
                invoked_parents=ctx.invoked_parents,
                args=list(args),
                kwargs=kwargs,
                guild_id=ctx.guild.id if ctx.guild else None,
                channel_id=ctx.channel.id,
                user_id=ctx.author.id,
                duration_ms=duration,
            )

    return callback


def logged_app_command(coro: "AppCommandCallback[GroupT, P, T]"):
    @functools.wraps(coro)  # pyright: ignore[reportArgumentType]
    async def callback(
        self: "GroupT", interaction: "Interaction[Any]", *args, **kwargs
    ):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            execution_id=interaction.id,
            command_name=interaction.command.qualified_name
            if interaction.command
            else None,
            is_app_command=interaction.command is not None,
        )

        command_failed = False
        start_time_ns = time.perf_counter_ns()

        try:
            return await coro(self, interaction, *args, **kwargs)  # pyright: ignore[reportCallIssue]
        except Exception:
            command_failed = True
            raise
        finally:
            end_time_ns = time.perf_counter_ns()
            duration = (end_time_ns - start_time_ns) // 1_000_000
            _log = logger.aerror if command_failed else logger.ainfo

            await _log(
                "Command finished execution",
                tag="command_finished",
                args=list(args),
                kwargs=kwargs,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
                duration_ms=duration,
            )

    return callback


log_level = logging.DEBUG if config.dangerous.dev else logging.INFO

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(log_level)
discord_logger.addHandler(StructlogHandler(log_level))

chunithm_net_logger = logging.getLogger("chunithm_net")
chunithm_net_logger.setLevel(log_level)
chunithm_net_logger.addHandler(StructlogHandler(log_level))
