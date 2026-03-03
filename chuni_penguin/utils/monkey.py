# pyright: reportAttributeAccessIssue=false
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from typing import Any

    import aiohttp
    from discord.types.gateway import SessionStartLimit


def patch_json():
    import discord.utils

    from .json import json_dumps, json_loads

    discord.utils._from_json = json_loads
    discord.utils._to_json = json_dumps


def patch_parse_timestamp():
    import contextlib

    with contextlib.suppress(ImportError):
        import ciso8601  # pyright: ignore[reportMissingImports]
        import discord.utils

        discord.utils.parse_time = (
            lambda timestamp: None
            if timestamp is None
            else ciso8601.parse_datetime(timestamp)
        )


def patch_http_use_proxy(proxy: str):
    import discord.http

    discord.http.Route.BASE = f"{proxy}/api/v{discord.http.INTERNAL_API_VERSION}"


def patch_gateway_use_proxy(proxy: str):
    import discord.client
    import discord.errors
    import discord.gateway
    import discord.http
    import yarl

    class ProxiedClient(discord.client.Client):
        async def before_identify_hook(
            self, shard_id: int | None, *, initial: bool = False
        ) -> None:
            pass

        def is_ws_ratelimited(self) -> bool:
            return False

    class ProxiedHTTPClient(discord.http.HTTPClient):
        async def get_bot_gateway(self) -> tuple[int, str, "SessionStartLimit"]:
            try:
                data = await self.request(discord.http.Route("GET", "/gateway/bot"))
            except discord.errors.HTTPException as exc:
                raise discord.errors.GatewayNotFound from exc

            return data["shards"], proxy, data["session_start_limit"]

    class ProxiedReconnectWebSocket(discord.gateway.ReconnectWebSocket):
        def __init__(self, shard_id: int | None, *, resume: bool = False) -> None:
            self.shard_id: int | None = shard_id
            self.resume: bool = False
            self.op: str = "IDENTIFY"

    class ProxiedGatewayRatelimiter(discord.gateway.GatewayRatelimiter):
        async def block(self) -> None:
            pass

    original_from_client = discord.gateway.DiscordWebSocket.from_client
    original_init = discord.gateway.DiscordWebSocket.__init__
    original_send_as_json = discord.gateway.DiscordWebSocket.send_as_json

    class TransparentCompressionContext:
        COMPRESSION_TYPE = None

        def decompress(self, data: bytes, /) -> str | None:
            return data.decode("utf-8")

    class ProxiedDiscordWebSocket(discord.gateway.DiscordWebSocket):
        DEFAULT_GATEWAY = yarl.URL(proxy)

        def __init__(
            self,
            socket: "aiohttp.ClientWebSocketResponse",
            *,
            loop: "asyncio.AbstractEventLoop",
        ) -> None:
            original_init(self, socket, loop=loop)
            self._decompressor = TransparentCompressionContext()

        @classmethod
        async def from_client(
            cls,
            client: discord.client.Client,
            *,
            initial: bool = False,
            gateway: yarl.URL | None = None,
            shard_id: int | None = None,
            session: str | None = None,
            sequence: int | None = None,
            resume: bool = False,
            encoding: str = "json",
            compress: bool = False,
        ):
            return await original_from_client(
                client,
                initial=initial,
                gateway=gateway,
                shard_id=shard_id,
                session=session,
                sequence=sequence,
                resume=resume,
                encoding=encoding,
                compress=False,  # gateway-proxy doesn't like compression
            )

        def is_ratelimited(self) -> bool:
            return False

        async def send_as_json(self, data: "Any") -> None:
            try:
                if data["op"] == self.IDENTIFY:
                    data["d"]["compress"] = False
            except KeyError:
                pass

            return await original_send_as_json(self, data)

    discord.client.Client.before_identify_hook = ProxiedClient.before_identify_hook
    discord.client.Client.is_ws_ratelimited = ProxiedClient.is_ws_ratelimited
    discord.http.HTTPClient.get_bot_gateway = ProxiedHTTPClient.get_bot_gateway
    discord.gateway.ReconnectWebSocket.__init__ = ProxiedReconnectWebSocket.__init__
    discord.gateway.GatewayRatelimiter.block = ProxiedGatewayRatelimiter.block
    discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY = (
        ProxiedDiscordWebSocket.DEFAULT_GATEWAY
    )
    discord.gateway.DiscordWebSocket.__init__ = ProxiedDiscordWebSocket.__init__
    discord.gateway.DiscordWebSocket.from_client = ProxiedDiscordWebSocket.from_client
    discord.gateway.DiscordWebSocket.is_ratelimited = (
        ProxiedDiscordWebSocket.is_ratelimited
    )
    discord.gateway.DiscordWebSocket.send_as_json = ProxiedDiscordWebSocket.send_as_json


def patch_all():
    import os

    patch_json()
    patch_parse_timestamp()

    if proxy := os.environ.get("DISCORD_HTTP_PROXY"):
        patch_http_use_proxy(proxy)

    if proxy := os.environ.get("DISCORD_GATEWAY_PROXY"):
        patch_gateway_use_proxy(proxy)
