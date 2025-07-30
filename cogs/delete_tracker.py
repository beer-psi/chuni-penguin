import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

import discord
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from bot import ChuniBot

EDIT_TRACKER_MAX_DURATION = 5 * 60  # five minutes


@dataclass
class CachedInvocation:
    user_message: discord.Message
    bot_response: discord.Message


class DeleteTrackerCog(commands.Cog, name="DeleteTracker"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot: "ChuniBot" = bot

        self._cache: dict[int, CachedInvocation] = {}
        self._cache_lock: asyncio.Lock = asyncio.Lock()

    @override
    async def cog_load(self) -> None:
        self._purge_expired_invocations.start()

    @override
    async def cog_unload(self) -> None:
        self._purge_expired_invocations.stop()

    @tasks.loop(seconds=EDIT_TRACKER_MAX_DURATION)
    async def _purge_expired_invocations(self):
        ttl = timedelta(seconds=EDIT_TRACKER_MAX_DURATION)

        async with self._cache_lock:
            for k, v in self._cache.items():
                last_update = v.user_message.edited_at or v.user_message.created_at
                age = datetime.now(UTC) - last_update

                if age >= ttl:
                    del self._cache[k]

    async def track_command(
        self, user_message: discord.Message, bot_response: discord.Message
    ):
        async with self._cache_lock:
            if (cached_invocation := self._cache.get(user_message.id)) is not None:
                cached_invocation.bot_response = bot_response
            else:
                self._cache[user_message.id] = CachedInvocation(
                    user_message, bot_response
                )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        async with self._cache_lock:
            if (cached_invocation := self._cache.pop(payload.message_id, None)) is None:
                return

        await cached_invocation.bot_response.delete()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(DeleteTrackerCog(bot))
