# pyright: reportAttributeAccessIssue=false
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

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
    import sys
    import time

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

    class ProxiedGatewayRatelimiter(discord.gateway.GatewayRatelimiter):
        async def block(self) -> None:
            pass

    original_init = discord.gateway.DiscordWebSocket.__init__
    original_from_client = discord.gateway.DiscordWebSocket.from_client

    class TransparentCompressionContext:
        COMPRESSION_TYPE = None

        def decompress(self, data: bytes, /) -> str | None:
            return data.decode("utf-8")

    class SilentKeepAliveHandler(discord.gateway.KeepAliveHandler):
        def ack(self) -> None:
            ack_time = time.perf_counter()
            self._last_ack = ack_time
            self.latency = ack_time - self._last_send

    class ProxiedDiscordWebSocket(discord.gateway.DiscordWebSocket):
        def __init__(
            self,
            socket: "aiohttp.ClientWebSocketResponse",
            *,
            loop: "asyncio.AbstractEventLoop",
        ) -> None:
            original_init(self, socket, loop=loop)
            self._decompressor = TransparentCompressionContext()

        @classmethod
        def from_client(cls, *args, **kwargs):
            kwargs["compress"] = False

            return original_from_client(*args, **kwargs)

        async def identify(self) -> None:
            from discord.gateway import _log

            """Sends the IDENTIFY packet."""
            payload = {
                "op": self.IDENTIFY,
                "d": {
                    "token": self.token,
                    "properties": {
                        "os": sys.platform,
                        "browser": "discord.py",
                        "device": "discord.py",
                    },
                    "compress": False,  # disable compression in gateway-proxy too
                    "large_threshold": 250,
                },
            }

            if self.shard_id is not None and self.shard_count is not None:
                payload["d"]["shard"] = [self.shard_id, self.shard_count]

            state = self._connection
            if state._activity is not None or state._status is not None:
                payload["d"]["presence"] = {
                    "status": state._status,
                    "game": state._activity,
                    "since": 0,
                    "afk": False,
                }

            if state._intents is not None:
                payload["d"]["intents"] = state._intents.value

            await self.call_hooks(
                "before_identify", self.shard_id, initial=self._initial_identify
            )
            await self.send_as_json(payload)
            _log.debug("Shard ID %s has sent the IDENTIFY payload.", self.shard_id)

    discord.client.Client.before_identify_hook = ProxiedClient.before_identify_hook
    discord.client.Client.is_ws_ratelimited = ProxiedClient.is_ws_ratelimited

    discord.http.HTTPClient.get_bot_gateway = ProxiedHTTPClient.get_bot_gateway

    discord.gateway.GatewayRatelimiter.block = ProxiedGatewayRatelimiter.block

    discord.gateway.KeepAliveHandler.ack = SilentKeepAliveHandler.ack

    discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(proxy)
    discord.gateway.DiscordWebSocket.__init__ = ProxiedDiscordWebSocket.__init__
    discord.gateway.DiscordWebSocket.from_client = ProxiedDiscordWebSocket.from_client
    discord.gateway.DiscordWebSocket.is_ratelimited = lambda self: False
    discord.gateway.DiscordWebSocket.identify = ProxiedDiscordWebSocket.identify


def patch_all():
    import os

    patch_json()
    patch_parse_timestamp()

    if proxy := os.environ.get("DISCORD_HTTP_PROXY"):
        patch_http_use_proxy(proxy)

    if proxy := os.environ.get("DISCORD_GATEWAY_PROXY"):
        patch_gateway_use_proxy(proxy)
