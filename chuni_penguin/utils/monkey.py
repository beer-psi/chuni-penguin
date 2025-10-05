from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    import discord.errors
    import discord.gateway
    import discord.http
    import yarl

    async def get_bot_gateway(
        self: discord.http.HTTPClient,
    ) -> tuple[int, str, "SessionStartLimit"]:
        try:
            data = await self.request(discord.http.Route("GET", "/gateway/bot"))
        except discord.errors.HTTPException as exc:
            raise discord.errors.GatewayNotFound from exc

        return data["shards"], proxy, data["session_start_limit"]

    discord.http.HTTPClient.get_bot_gateway = get_bot_gateway
    discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY = yarl.URL(proxy)
    discord.gateway.DiscordWebSocket.is_ratelimited = lambda self: False


def patch_all():
    import os

    patch_json()
    patch_parse_timestamp()

    if proxy := os.environ.get("DISCORD_HTTP_PROXY"):
        patch_http_use_proxy(proxy)

    if proxy := os.environ.get("DISCORD_GATEWAY_PROXY"):
        patch_gateway_use_proxy(proxy)
