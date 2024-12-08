import traceback
from typing import TYPE_CHECKING, cast

import aiohttp
import discord
import httpx
from discord import Webhook, app_commands
from discord.app_commands import AppCommandError
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

    async def cog_load(self) -> None:
        self._old_tree_error = self.bot.tree.on_error
        self.bot.tree.on_error = self.tree_on_error

    async def cog_unload(self) -> None:
        self.bot.tree.on_error = self._old_tree_error

    async def tree_on_error(
        self,
        interaction: discord.Interaction["ChuniBot"],
        error: AppCommandError,
    ):
        exc: Exception = error

        while hasattr(exc, "original"):
            exc = cast(Exception, exc.original)

        embed, _ = await self._construct_error_embed("/", exc)

        if embed.description is not None:
            await interaction.edit_original_response(embed=embed)
            return

        logger.exception(
            "Unhandled exception in app command %s",
            interaction.command.name if interaction.command else "unknown",
            exc_info=exc,
        )

        # fmt: off
        embed.description = (
            "An unhandled error occurred. It dropped this message:\n"
            "```python\n"
            f"{''.join(traceback.format_exception_only(exc))}\n"
            "```\n"
            "The error has been logged. Please try again later."
        )
        # fmt: on

        await interaction.edit_original_response(embed=embed)
        await self._submit_error_to_webhook(interaction.command, exc)

        return

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
            exc = cast(Exception, exc.original)

        embed, delete_after = await self._construct_error_embed(ctx.prefix or "c>", exc)

        if embed.description is not None:
            return await ctx.reply(
                embed=embed,
                mention_author=False,
                delete_after=delete_after,  # type: ignore[reportCallIssue, reportArgumentType]
            )

        logger.exception("Unhandled exception in command %s", ctx.command, exc_info=exc)

        # fmt: off
        embed.description = (
            "An unhandled error occurred. It dropped this message:\n"
            "```python\n"
            f"{''.join(traceback.format_exception_only(exc))}\n"
            "```\n"
            "The error has been logged. Please try again later."
        )
        # fmt: on

        await ctx.reply(embed=embed, mention_author=False)
        await self._submit_error_to_webhook(ctx.command, exc)

        return None

    async def _construct_error_embed(self, prefix: str, exc: Exception):
        embed = discord.Embed(
            color=discord.Color.red(),
            title="Error",
        )
        delete_after: float | None = None

        if isinstance(exc, MaintenanceException):
            embed.description = "CHUNITHM-NET is currently undergoing maintenance. Please try again later."
        elif isinstance(exc, ChuniNetError):
            embed.description = f"CHUNITHM-NET error {exc.code}: {exc.description}"
        elif isinstance(exc, InvalidTokenException):
            embed.description = (
                f"The token has expired. Please log in again with `{prefix}login` in my DMs.\n"
                "\n"
                "To prevent being logged out constantly:\n"
                "- Don't quickly switch between using the bot and visiting CHUNITHM-NET directly\n"
                "- Log in using a separate incognito session\n"
                "- Use SEGA ID instead of social media login (especially Twitter)"
            )
        elif isinstance(exc, InvalidFriendCode):
            embed.description = "Could not find anyone with this friend code. Please double-check and try again."
        elif isinstance(exc, ChuniNetException):
            embed.description = (
                "An error occurred while communicating with CHUNITHM-NET. Please try again later (or re-login).\n"
                "\n"
                "Detailed error:\n"
                "```python\n"
                f"{traceback.format_exception_only(exc)}\n"
                "```"
            )

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
            embed.description = str(exc)

        if isinstance(exc, httpx.TimeoutException):
            embed.description = "Timed out trying to connect to CHUNITHM-NET."

        if isinstance(exc, httpx.TransportError):
            embed.description = (
                "An unknown network error occured trying to connect to CHUNITHM-NET.\n"
                "\n"
                "Detailed error:\n"
                "```python\n"
                f"{traceback.format_exception_only(exc)}\n"
                "```"
            )

        return embed, delete_after

    async def _submit_error_to_webhook(
        self,
        command: commands.Command
        | app_commands.Command
        | app_commands.ContextMenu
        | None,
        exc: Exception,
    ):
        if (webhook_url := config.bot.error_reporting_webhook) is None:
            return

        command_name = command.name if command else None

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)

            content = (
                f"## Exception in command {command_name}\n\n"
                "```python\n"
                f"{(''.join(traceback.format_exception(exc)))[-1961 + len(str(command_name)):]}"
                "```"
            )

            client_user = cast(discord.ClientUser, self.bot.user)
            await webhook.send(
                username=client_user.display_name,
                avatar_url=client_user.display_avatar.url,
                content=content,
                allowed_mentions=discord.AllowedMentions.none(),
            )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(EventsCog(bot))
