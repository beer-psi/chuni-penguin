import traceback
from typing import TYPE_CHECKING, cast

import aiohttp
import discord
import httpx
from discord import Webhook
from discord.ext import commands
from discord.ext.commands import Context

from chunithm_net.exceptions import (
    ChuniNetError,
    ChuniNetException,
    InvalidFriendCode,
    InvalidTokenException,
    MaintenanceException,
)
from utils.config import config
from utils.logging import logger

if TYPE_CHECKING:
    from bot import ChuniBot


class EventsCog(commands.Cog, name="Events"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx: Context):
        pass

    @commands.Cog.listener()
    async def on_command_error(
        self,
        ctx: Context,
        error: commands.errors.CommandInvokeError,
    ):
        if isinstance(error, commands.CommandNotFound):
            return None

        exc = error
        while hasattr(exc, "original"):
            exc = exc.original  # type: ignore[reportGeneralTypeIssues]

        embed = discord.Embed(
            color=discord.Color.red(),
            title="Error",
        )
        delete_after = None

        if isinstance(exc, MaintenanceException):
            embed.description = "CHUNITHM-NET is currently undergoing maintenance. Please try again later."
        elif isinstance(exc, ChuniNetError):
            embed.description = f"CHUNITHM-NET error {exc.code}: {exc.description}"
        elif isinstance(exc, InvalidTokenException):
            embed.description = f"The token has expired. Please log in again with `{ctx.prefix}login` in my DMs."
        elif isinstance(exc, InvalidFriendCode):
            embed.description = "Could not find anyone with this friend code. Please double-check and try again."
        elif isinstance(exc, ChuniNetException):
            embed.description = "An error occurred while communicating with CHUNITHM-NET. Please try again later (or re-login)."
            if self.bot.dev:
                embed.description += f"\nDetailed error: {exc}"

        if isinstance(exc, commands.errors.CommandOnCooldown):
            embed.description = (
                f"You're too fast. Take a break for {exc.retry_after:.2f} seconds."
            )
            delete_after = exc.retry_after
        if isinstance(exc, commands.errors.ExpectedClosingQuoteError):
            embed.description = "You're missing a quote somewhere. Perhaps you're using the wrong kind of quote (`\"` vs `”`)?"
        if isinstance(exc, commands.errors.UnexpectedQuoteError):
            embed.description = (
                f"Unexpected quote mark, {exc.quote!r}, in non-quoted string. If this was intentional, "
                "escape the quote with a backslash (\\\\)."
            )
        if isinstance(exc, commands.errors.InvalidEndOfQuotedStringError):
            embed.description = str(exc)
        if isinstance(
            exc, (commands.errors.NotOwner, commands.errors.MissingPermissions)
        ):
            embed.description = "Insufficient permissions."
        if isinstance(exc, commands.BadLiteralArgument):
            to_string = [repr(x) for x in exc.literals]
            if len(to_string) > 2:
                fmt = "{}, or {}".format(", ".join(to_string[:-1]), to_string[-1])
            else:
                fmt = " or ".join(to_string)
            embed.description = f"`{exc.param.displayed_name or exc.param.name}` must be one of {fmt}, received {exc.argument!r}"
        if isinstance(exc, commands.CommandError) and not isinstance(
            exc,
            (
                commands.CommandNotFound,
                commands.ConversionError,
            ),
        ):
            embed.description = str(error)

        if isinstance(exc, httpx.TimeoutException):
            embed.description = "Timed out trying to connect to CHUNITHM-NET."

        if isinstance(exc, httpx.TransportError):
            embed.description = (
                "An unknown network error occured trying to connect to CHUNITHM-NET."
            )

        if embed.description is not None:
            return await ctx.reply(
                embed=embed,
                mention_author=False,
                delete_after=delete_after,  # type: ignore[reportCallIssue, reportArgumentType]
            )

        logger.error("Exception in command %s", ctx.command, exc_info=exc)
        embed.description = (
            "Something really terrible happened. "
            f"The owner <@{self.bot.owner_id}> has been notified.\n"
            "Please try again in a couple of hours."
        )
        await ctx.reply(embed=embed, mention_author=False)

        if webhook_url := config.bot.error_reporting_webhook:
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(webhook_url, session=session)

                content = (
                    f"## Exception in command {ctx.command}\n\n"
                    "```python\n"
                    f"{(''.join(traceback.format_exception(exc)))[-1961 + len(str(ctx.command)):]}"
                    "```"
                )

                client_user = cast(discord.ClientUser, self.bot.user)
                await webhook.send(
                    username=client_user.display_name,
                    avatar_url=client_user.display_avatar.url,
                    content=content,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        return None


async def setup(bot: "ChuniBot"):
    await bot.add_cog(EventsCog(bot))
