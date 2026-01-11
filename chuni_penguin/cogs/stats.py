import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

import discord
from discord.ext import commands, tasks
from discord.ext.commands.hybrid import HybridAppCommand
from sqlalchemy import insert
from sqlalchemy.exc import SQLAlchemyError

from chuni_penguin.context import PenguinContext
from chuni_penguin.database import CommandUse
from chuni_penguin.logging import logger

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class CommandUseBulkEntry(TypedDict):
    guild_id: int | None
    channel_id: int
    author_id: int
    prefix: str
    command: str
    is_failure: bool
    is_app_command: bool
    created_at: datetime


class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot: "ChuniBot"):
        self.bot = bot

        self._stats_batch: list[CommandUseBulkEntry] = []
        self._stats_batch_lock: asyncio.Lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.stats_bulk_insert_loop.add_exception_type(SQLAlchemyError)
        self.stats_bulk_insert_loop.start()

    async def cog_unload(self) -> None:
        self.stats_bulk_insert_loop.stop()

    @tasks.loop(seconds=10)
    async def stats_bulk_insert_loop(self):
        async with self._stats_batch_lock:
            if not self._stats_batch:
                return

            async with self.bot.begin_db_session() as session:
                await session.execute(insert(CommandUse), self._stats_batch)
                await session.commit()

            await logger.adebug(
                "Registered command uses to the database.",
                tag="command_uses_saved",
                count=len(self._stats_batch),
            )
            self._stats_batch.clear()

    async def register_command_use(self, ctx: PenguinContext):
        if ctx.command is None:
            return

        async with self._stats_batch_lock:
            self._stats_batch.append(
                {
                    "guild_id": ctx.guild.id if ctx.guild is not None else None,
                    "channel_id": ctx.channel.id,
                    "author_id": ctx.author.id,
                    "prefix": ctx.clean_prefix,
                    "command": ctx.command.qualified_name,
                    "is_failure": ctx.command_failed,
                    "is_app_command": ctx.interaction is not None,
                    "created_at": ctx.message.created_at,
                }
            )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: PenguinContext):
        await self.register_command_use(ctx)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction["ChuniBot"]):
        if interaction.type != discord.InteractionType.application_command:
            return

        if (command := interaction.command) is None:
            return

        # Hybrid commands are already counted via on_command_completion
        if isinstance(command, HybridAppCommand):
            return

        if interaction.channel_id is None:
            await logger.awarning(
                "Interaction channel ID is null", interaction=interaction
            )
            return

        async with self._stats_batch_lock:
            self._stats_batch.append(
                {
                    "guild_id": interaction.guild_id,
                    "channel_id": interaction.channel_id,
                    "author_id": interaction.user.id,
                    "prefix": "/",
                    "command": command.qualified_name,
                    "is_failure": interaction.command_failed,
                    "is_app_command": True,
                    "created_at": interaction.created_at,
                }
            )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(StatsCog(bot))
