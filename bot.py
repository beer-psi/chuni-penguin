import asyncio
import contextlib
import signal
import sys
import time
from collections.abc import Callable, Coroutine
from datetime import timedelta
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any, cast, override

import discord
import discord.utils
from discord.ext import commands
from discord.ext.track_edits import EditTrackerCog
from sqlalchemy import select, text

from cogs import COG_LIST
from cogs.gaming.states.base import GuessingGameSkippableState
from database.models import Denylist, Prefix
from utils import json_dumps, json_loads
from utils.command_tree import PenguinCommandTree
from utils.config import config
from utils.context import PenguinContext
from utils.event_loop import get_event_loop
from utils.logging import logger

if TYPE_CHECKING:
    from cogs.botutils import UtilsCog
    from cogs.database import DatabaseCog
    from cogs.gaming import GamingCog
    from cogs.web import WebCog


BOT_DIR = Path(__file__).parent


discord.utils._from_json = json_loads
discord.utils._to_json = json_dumps

with contextlib.suppress(ImportError):
    import ciso8601

    discord.utils.parse_time = (
        lambda timestamp: ciso8601.parse_datetime(timestamp) if timestamp else None
    )


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


def ensure_text_command_permissions():
    check = commands.bot_has_permissions(
        send_messages=True,
        embed_links=True,
    )
    thread_check = commands.bot_has_permissions(
        send_messages_in_threads=True,
        embed_links=True,
    )

    async def predicate(ctx: commands.Context):
        if ctx.interaction is not None:
            return True

        if isinstance(ctx.channel, discord.Thread):
            return await thread_check.predicate(ctx)

        return await check.predicate(ctx)

    return commands.check(predicate)


class ChuniBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            command_prefix=guild_specific_prefix(config.bot.default_prefix),
            tree_cls=PenguinCommandTree,
            intents=discord.Intents(
                guilds=True,
                voice_states=True,
                messages=True,
                typing=True,
                message_content=True,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        self.add_check(ensure_text_command_permissions().predicate)

        self.launch_time: float = -1
        self.prefixes: dict[int, str] = {}
        self.command_start_time: dict[commands.Context, int] = {}
        self.denylist: set[int] = set()

    async def start(self, *args, **kwargs):
        self.launch_time = time.time()
        return await super().start(*args, **kwargs)

    async def setup_hook(self) -> None:
        # Database setup
        if config.dangerous.dev:
            await self.load_extension("jishaku")

        await self.add_cog(EditTrackerCog(self, max_duration=timedelta(minutes=5)))

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
                await logger.aexception(
                    "Extension raised error",
                    tag="extension_error",
                    extension=cog,
                    exc_info=e,
                )

        # Load guild prefixes
        async with self.begin_db_session() as session:
            prefixes = (await session.execute(select(Prefix))).scalars()
            denylist = (await session.execute(select(Denylist))).scalars()

        self.prefixes = {prefix.guild_id: prefix.prefix for prefix in prefixes}
        self.denylist = {d.object_id for d in denylist}

        await logger.ainfo(
            "Loaded guild prefixes",
            tag="load_guild_prefix",
            prefix_count=len(self.prefixes),
        )

        tree = cast(PenguinCommandTree, self.tree)
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

    @override
    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        *,
        cls: type[PenguinContext] = PenguinContext,
    ):
        try:
            ctx = await super().get_context(origin, cls=cls)
        except Exception as e:
            await logger.aexception(
                "could not get context", tag="error_get_context", exc_info=e
            )
            raise

        if ctx.command is not None:
            ctx.user_config = await self.utils.fetch_user_config(ctx.author.id)

        return ctx

    @override
    async def process_commands(self, message: discord.Message, /) -> None:
        if message.author.bot:
            return

        ctx = await self.get_context(message)

        if await self.is_owner(ctx.author):
            await self.invoke(ctx)
            return

        if ctx.author.id in self.denylist:
            return

        if ctx.guild is not None and ctx.guild.id in self.denylist:
            return

        await self.invoke(ctx)

    @override
    async def _run_event(
        self,
        coro: Callable[..., Coroutine[Any, Any, Any]],
        event_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            await logger.aerror(
                "exception in event handler",
                tag="error_event_handler",
                event_method=event_name,
                args=args,
                kwargs=kwargs,
                exc_info=e,
            )

            with contextlib.suppress(asyncio.CancelledError):
                await self.on_error(event_name, *args, **kwargs)

    @override
    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        pass

    @property
    def utils(self) -> "UtilsCog":
        return self.get_cog("Utils")  # pyright: ignore[reportReturnType]

    @property
    def engine(self):
        return cast("DatabaseCog", self.get_cog("Database")).engine

    @property
    def begin_db_session(self):
        return cast("DatabaseCog", self.get_cog("Database")).sessionmaker

    @property
    def app(self):
        return cast("WebCog", self.get_cog("Web")).web_app

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

        timeout_tasks: set[asyncio.Task] = set()

        for view in self._connection._view_store._synced_message_views.values():
            if view.is_finished():
                continue

            if view.timeout is not None:
                timeout_tasks.add(
                    asyncio.create_task(
                        view.on_timeout(), name=f"discord-ui-view-timeout-{view.id}"
                    )
                )

        if len(timeout_tasks) > 0:
            await asyncio.wait(timeout_tasks)

        await super().close()


def guild_specific_prefix(default: str):
    async def inner(bot: ChuniBot, msg: discord.Message) -> list[str]:
        prefixes = commands.when_mentioned(bot, msg)

        if msg.guild is None:
            prefixes.append(default)
        else:
            prefixes.append(bot.prefixes.get(msg.guild.id, default))

            if (role := msg.guild.self_role) is not None:
                prefixes.append(f"{role.mention} ")

        return prefixes

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
