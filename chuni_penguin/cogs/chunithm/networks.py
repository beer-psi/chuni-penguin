import contextlib
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import discord
import httpx
import httpx_aiohttp
import msgspec
from discord.ext import commands, tasks
from sqlalchemy import select, update

from chuni_penguin.config import config
from chuni_penguin.database import Chart, Cookie
from chuni_penguin.logging import logger
from chuni_penguin.networks.base import Network
from chuni_penguin.networks.chunithm_net import ChunithmNet
from chuni_penguin.networks.kamaitachi import Kamaitachi
from chuni_penguin.networks.types import Difficulty
from chuni_penguin.utils import AsyncRcContextManager

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class KeiyoushiUserAgents(msgspec.Struct):
    recommended: str
    desktop: list[str]
    mobile: list[str]


class NetworksCog(commands.Cog, command_attrs={"hidden": True}):
    def __init__(self, bot: "ChuniBot"):
        self.bot = bot
        self.user_agents: KeiyoushiUserAgents | None = None

        self._chuni_net_sessions: dict[int, AsyncRcContextManager[ChunithmNet]] = {}

    async def cog_load(self) -> None:
        self._update_user_agents.start()

    async def cog_unload(self) -> None:
        self._update_user_agents.stop()

    @tasks.loop(hours=24)
    async def _update_user_agents(self):
        async with httpx.AsyncClient(
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5)
        ) as client:
            resp = await client.get(
                "https://keiyoushi.github.io/user-agents/user-agents.min.json"
            )

            if resp.status_code != 200:
                logger.warning(
                    "could not update user agents",
                    tag="update_user_agent_failed",
                    status_code=resp.status_code,
                )
                return

            try:
                self.user_agents = msgspec.json.decode(
                    resp.content, type=KeiyoushiUserAgents
                )
                logger.debug(
                    "updated user agents",
                    tag="update_user_agent_success",
                    count=len(self.user_agents.desktop)
                    + len(self.user_agents.mobile)
                    + 1,  # for recommended UA
                )
            except msgspec.DecodeError as e:
                logger.exception(
                    "could not parse user agents",
                    tag="update_user_agent_failed",
                    exc_info=e,
                )
                return

    @_update_user_agents.error
    async def _update_user_agents_error(self, exc: BaseException):
        logger.exception(
            "unhandled exception updating user agents",
            tag="update_useragent_failed",
            exc_info=exc,
        )

    async def _get_kt_chart_id(self, song_id: int, difficulty: Difficulty):
        async with self.bot.begin_db_session() as session:
            query = select(Chart).where(
                (Chart.song_id == song_id) & (Chart.difficulty == difficulty.short())
            )
            result = (await session.execute(query)).scalar_one_or_none()

        return result.tachi_chart_id if result is not None else None

    async def _get_kt_chart_ids(self, song_id: int):
        async with self.bot.begin_db_session() as session:
            query = select(Chart).where(Chart.song_id == song_id)
            results = await session.execute(query)

        return [
            result.tachi_chart_id
            for result in results.scalars()
            if result.tachi_chart_id is not None
        ]

    @contextlib.asynccontextmanager
    async def kamaitachi(self, token: str):
        async with Kamaitachi(token) as client:
            client.get_kt_chart_id = self._get_kt_chart_id
            client.get_kt_chart_ids = self._get_kt_chart_ids

            yield client

    @contextlib.asynccontextmanager
    async def chunithm_net(self, user_id: int, lwp_cookies: str):
        if (rc := self._chuni_net_sessions.get(user_id)) and rc.refcount > 0:
            logger.debug(
                "using cached chunithm-net session",
                tag="cached_chunithm_net_session",
                user_id=user_id,
                refcount=rc.refcount,
            )

            async with rc as session:
                yield session

            return

        session = ChunithmNet(lwp_cookies)

        if session.RANDOMIZE_USER_AGENT and self.user_agents is not None:
            session.user_agent = self.user_agents.desktop[
                (user_id >> 22) % len(self.user_agents.desktop)
            ]

        async def on_exit(session: ChunithmNet):
            async with self.bot.begin_db_session() as db_session:
                await db_session.execute(
                    update(Cookie)
                    .where(Cookie.discord_id == user_id)
                    .values(cookie=session.authentication)
                )
                await db_session.commit()

            del self._chuni_net_sessions[user_id]

        self._chuni_net_sessions[user_id] = AsyncRcContextManager(
            session, on_exit=[on_exit]
        )

        async with self._chuni_net_sessions[user_id] as session:
            yield session

    def _get_not_logged_in_message(
        self,
        network: type[Network] | None,
        author_id: int,
        target_id: int,
        *,
        is_interaction: bool,
    ):
        network_name = "" if network is None else f" to {network.NAME}"
        command_name = (
            "kamaitachi link"
            if network is not None and issubclass(network, Kamaitachi)
            else "login"
        )
        prefix = "/" if is_interaction else config.bot.default_prefix
        cta = " to log in." if is_interaction else " in my DMs to log in."

        if author_id == target_id:
            return f"You are not logged in{network_name}. Please send `{prefix}{command_name}`{cta}"

        return f"<@{target_id}> is not logged in{network_name}."

    @contextlib.asynccontextmanager
    async def network(
        self,
        ctx: commands.Context | discord.Interaction,
        id: int | None = None,
        *,
        kamaitachi: bool = False,
        chunithm_net: bool = False,
    ) -> AsyncGenerator[Network, None]:
        author_id = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        target_id = id or author_id
        is_interaction = (
            isinstance(ctx, discord.Interaction) or ctx.interaction is not None
        )
        user_config = await self.bot.utils.fetch_user_config(target_id)

        if user_config.privacy_mode and author_id != target_id:
            msg = f"<@{target_id}> is not logged in."
            raise commands.CommandError(msg)

        async with self.bot.begin_db_session() as session:
            stmt = select(Cookie).where(Cookie.discord_id == target_id)
            cookie = (await session.execute(stmt)).scalar_one_or_none()

        if cookie is None:
            msg = self._get_not_logged_in_message(
                None, author_id, target_id, is_interaction=is_interaction
            )
            raise commands.CommandError(msg)

        if kamaitachi:
            if cookie.kamaitachi_token is None:
                msg = self._get_not_logged_in_message(
                    Kamaitachi, author_id, target_id, is_interaction=is_interaction
                )
                raise commands.CommandError(msg)

            async with self.kamaitachi(cookie.kamaitachi_token) as client:
                yield client

            return

        if chunithm_net:
            if not cookie.cookie:
                msg = self._get_not_logged_in_message(
                    ChunithmNet, author_id, target_id, is_interaction=is_interaction
                )
                raise commands.CommandError(msg)

            async with self.chunithm_net(target_id, cookie.cookie) as client:
                yield client

            return

        if cookie.cookie.startswith("#LWP-Cookies-2.0"):
            async with self.chunithm_net(target_id, cookie.cookie) as client:
                yield client

            return

        if cookie.kamaitachi_token is not None:
            async with self.kamaitachi(cookie.kamaitachi_token) as client:
                yield client

            return

        msg = self._get_not_logged_in_message(
            None, author_id, target_id, is_interaction=is_interaction
        )
        raise commands.CommandError(msg)


async def setup(bot: "ChuniBot"):
    await bot.add_cog(NetworksCog(bot))
