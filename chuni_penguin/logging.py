import functools
import logging
import sys
import time
from typing import TYPE_CHECKING, Any

import structlog
from structlog.stdlib import BoundLogger

from chuni_penguin.config import config

if TYPE_CHECKING:
    from discord import Interaction
    from discord.app_commands.commands import CommandCallback as AppCommandCallback
    from discord.app_commands.commands import GroupT
    from discord.ext.commands._types import ContextT
    from discord.ext.commands.hybrid import CogT, CommandCallback, P, T

__all__ = ("logged_app_command", "logged_prefix_command", "logger")


log_level = logging.DEBUG if config.dangerous.dev else logging.INFO
shared_processors: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.dev.set_exc_info,
    structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
]
format_processors: list[structlog.typing.Processor] = [
    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
]

if config.dangerous.dev:
    format_processors.append(structlog.dev.ConsoleRenderer())
else:
    format_processors.append(structlog.processors.dict_tracebacks)
    format_processors.append(structlog.processors.JSONRenderer())

structlog.configure(
    processors=[
        *shared_processors,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

formatter = structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=[
        *shared_processors,
        structlog.stdlib.add_logger_name,
    ],
    processors=format_processors,
)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

for logger_name in ("chuni_penguin", "chunithm_net", "discord"):
    _logger = logging.getLogger(logger_name)
    _logger.addHandler(handler)
    _logger.setLevel(log_level)

logger: BoundLogger = structlog.get_logger("chuni_penguin")


def logged_prefix_command(coro: "CommandCallback[CogT, ContextT, P, T]"):
    @functools.wraps(coro)  # pyright: ignore[reportArgumentType]
    async def callback(self: "CogT", ctx: "ContextT", *args, **kwargs):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            execution_id=ctx.message.id,
            command_name=ctx.command.qualified_name if ctx.command else None,
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
                is_app_command=ctx.interaction is not None,
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
                is_app_command=interaction.command is not None,
                args=list(args),
                kwargs=kwargs,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
                duration_ms=duration,
            )

    return callback
