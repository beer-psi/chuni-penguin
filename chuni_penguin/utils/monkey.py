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
    import asyncio
    import concurrent.futures
    import sys
    import time
    import traceback

    import discord.client
    import discord.errors
    import discord.gateway
    import discord.http
    import yarl
    from discord.gateway import _log as _gateway_logger

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

    class TransparentCompressionContext:
        COMPRESSION_TYPE = None

        def decompress(self, data: bytes, /) -> str | None:
            return data.decode("utf-8")

    class KeepAliveHandler(discord.gateway.KeepAliveHandler):
        def _heartbeat_send_done_callback(
            self, future: concurrent.futures.Future[None]
        ):
            try:
                if future.exception() is None:
                    self._last_send = time.perf_counter()
            except concurrent.futures.CancelledError:
                pass

        def run(self) -> None:
            while not self._stop_ev.wait(self.interval):
                if self._last_recv + self.heartbeat_timeout < time.perf_counter():
                    _gateway_logger.warning(
                        "Shard ID %s has stopped responding to the gateway. Closing and restarting.",
                        self.shard_id,
                    )
                    coro = self.ws.close(4000)
                    f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                    try:
                        f.result()
                    except Exception:  # noqa: BLE001
                        _gateway_logger.exception(
                            "An error occurred while stopping the gateway. Ignoring."
                        )
                    except BaseException as exc:  # noqa: BLE001
                        _gateway_logger.debug(
                            "A BaseException was raised while stopping the gateway",
                            exc_info=exc,
                        )
                    finally:
                        self.stop()
                    return

                data = self.get_payload()

                _gateway_logger.debug(self.msg, self.shard_id, data["d"])

                coro = self.ws.send_heartbeat(data)
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                f.add_done_callback(self._heartbeat_send_done_callback)
                try:
                    # block until sending is complete
                    total = 0
                    while True:
                        try:
                            f.result(10)
                            break
                        except concurrent.futures.TimeoutError:
                            total += 10
                            try:
                                frame = sys._current_frames()[self._main_thread_id]
                            except KeyError:
                                msg = self.block_msg
                            else:
                                stack = "".join(traceback.format_stack(frame))
                                msg = f"{self.block_msg}\nLoop thread traceback (most recent call last):\n{stack}"
                            _gateway_logger.warning(msg, self.shard_id, total)

                except Exception:  # noqa: BLE001
                    self.stop()

    original_init = discord.gateway.DiscordWebSocket.__init__
    original_from_client = discord.gateway.DiscordWebSocket.from_client

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

        # TODO: The only difference here is that we disable compression on gateway.
        # It would be neat to not have to repeat all this code...
        async def identify(self) -> None:
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
            _gateway_logger.debug(
                "Shard ID %s has sent the IDENTIFY payload.", self.shard_id
            )

    discord.client.Client.before_identify_hook = ProxiedClient.before_identify_hook
    discord.client.Client.is_ws_ratelimited = ProxiedClient.is_ws_ratelimited

    discord.http.HTTPClient.get_bot_gateway = ProxiedHTTPClient.get_bot_gateway

    discord.gateway.GatewayRatelimiter.block = ProxiedGatewayRatelimiter.block

    discord.gateway.KeepAliveHandler._heartbeat_send_done_callback = (
        KeepAliveHandler._heartbeat_send_done_callback
    )
    discord.gateway.KeepAliveHandler.run = KeepAliveHandler.run

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
