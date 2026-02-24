import asyncio
import contextlib
import time
from collections.abc import Callable, Coroutine
from datetime import timedelta
from types import ModuleType
from typing import TYPE_CHECKING, Any, cast, override

import discord
import hishel
import httpx
import httpx_aiohttp
from discord.ext import commands
from discord.ext.track_edits import EditTrackerCog
from sqlalchemy import select, text

from chuni_penguin.ui.components import BannedEmbed

from .cogs import COG_LIST
from .command_tree import PenguinCommandTree
from .config import config
from .constants import CACHE_DIR
from .context import PenguinContext, PenguinGuildContext
from .database import Denylist, Prefix
from .logging import logger
from .utils import HishelMsgspecSerializer

if TYPE_CHECKING:
    from .cogs.botutils import UtilsCog
    from .cogs.chunithm.networks import NetworksCog
    from .cogs.database import DatabaseCog
    from .cogs.gaming import GamingCog
    from .cogs.permissions import PermissionsCog
    from .cogs.web import WebCog


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
    if TYPE_CHECKING:
        _BotBase__extensions: dict[str, ModuleType]
        _BotBase__cogs: dict[str, commands.Cog]

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
        self.denylist: dict[int, Denylist] = {}
        self.caching_http_client = hishel.AsyncCacheClient(
            timeout=httpx.Timeout(timeout=60.0),
            follow_redirects=True,
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5),
            controller=hishel.Controller(
                cacheable_methods=["GET", "HEAD"],
                allow_heuristics=True,
                allow_stale=True,
            ),
            storage=hishel.AsyncFileStorage(
                serializer=HishelMsgspecSerializer(),
                base_path=CACHE_DIR,
                check_ttl_every=300,
            ),
        )

        self._close_games_count: int = 0

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
            except ModuleNotFoundError as e:
                await logger.aexception(
                    "Extension module not found",
                    tag="extension_not_found",
                    extension=cog,
                    exc_info=e,
                )

        # Load guild prefixes
        async with self.begin_db_session() as session:
            prefixes = (await session.execute(select(Prefix))).scalars()
            denylist = (await session.execute(select(Denylist))).scalars()

        self.prefixes = {prefix.guild_id: prefix.prefix for prefix in prefixes}
        self.denylist = {d.object_id: d for d in denylist}

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

                if not config.dangerous.dev:
                    await self.tree.sync()
                    await session.execute(
                        text(f"PRAGMA user_version={current_tree_hash}")
                    )

        self.add_check(self.permissions.permissions_check)

    @override
    async def get_context(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        origin: discord.Message | discord.Interaction,
        *,
        cls: type[PenguinContext] = PenguinContext,
    ):
        if origin.guild is not None:
            cls = PenguinGuildContext

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

        ban_entry: Denylist | None = None
        server_name: str | None = None

        if ctx.author.id in self.denylist:
            ban_entry = self.denylist[ctx.author.id]
        elif ctx.guild is not None and ctx.guild.id in self.denylist:
            ban_entry = self.denylist[ctx.guild.id]
            server_name = ctx.guild.name

        if ban_entry is not None and ctx.invoked_with is not None:
            with contextlib.suppress(discord.HTTPException):
                dm_channel = ctx.author.dm_channel

                if dm_channel is None:
                    dm_channel = await ctx.author.create_dm()

                embed = BannedEmbed(
                    client=self,
                    entry=ban_entry,
                    server_name=server_name,
                    support_server_invite=config.bot.support_server_invite,
                )

                if ctx.channel == dm_channel:
                    await ctx.reply(embed=embed)
                else:
                    await dm_channel.send(embed=embed)

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
    def database(self) -> "DatabaseCog":
        return cast("DatabaseCog", self.get_cog("Database"))

    @property
    def engine(self):
        return cast("DatabaseCog", self.get_cog("Database")).engine

    @property
    def begin_db_session(self):
        return cast("DatabaseCog", self.get_cog("Database")).sessionmaker

    @property
    def app(self):
        return cast("WebCog", self.get_cog("Web")).web_app

    @property
    def chunithm_networks(self) -> "NetworksCog":
        return self.get_cog("NetworksCog")  # pyright: ignore[reportReturnType]

    @property
    def permissions(self) -> "PermissionsCog":
        return self.get_cog("Permissions")  # pyright: ignore[reportReturnType]

    async def _close_games(self):
        gaming = cast("GamingCog | None", self.get_cog("Games"))

        if gaming is not None:
            self._close_games_count += 1

            if self._close_games_count <= 1:
                gaming.shutting_down = True

                warning_embed = discord.Embed(
                    color=discord.Color.yellow(),
                    title="Warning",
                    description="I'll be going down for an update soon. Please finish your game in five minutes.",
                )

                async with gaming.game_sessions.read() as game_sessions:
                    await asyncio.gather(
                        *[
                            s.channel.send(embed=warning_embed)
                            for s in set(game_sessions.values())
                        ]
                    )

            if len(gaming.game_tasks) > 0 and self._close_games_count <= 1:
                _, pending = await asyncio.wait(gaming.game_tasks, timeout=300)
            else:
                pending = gaming.game_tasks

            async with gaming.game_sessions.read() as game_sessions:
                for session in game_sessions.values():
                    await session.stop(self.user)  # pyright: ignore[reportArgumentType]

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

        # Unload extensions in reverse order (LIFO) since later extensions depend
        # on previous extensions being available - discord.py's default behavior is FIFO
        for extension in reversed(tuple(self._BotBase__extensions)):
            with contextlib.suppress(Exception):
                await self.unload_extension(extension)

        for cog in reversed(tuple(self._BotBase__cogs)):
            with contextlib.suppress(Exception):
                await self.remove_cog(cog)

        await super().close()
