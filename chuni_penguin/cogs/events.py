import contextlib
import io
import json
import traceback
from pprint import pformat
from typing import TYPE_CHECKING, cast

import aiohttp
import discord
import httpx
from discord import DiscordServerError, Webhook, app_commands
from discord.app_commands import AppCommandError
from discord.ext import commands, songbird
from discord.ext.commands import Context

from chuni_penguin.adapters.chunithm_net.errors import ChuniNetError
from chuni_penguin.adapters.errors import (
    AuthenticationError,
    HTTPError,
    InvalidFriendCode,
    MaintenanceError,
    NetworkError,
    NoCardsRegistered,
)
from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.errors import Banned, CommandDisabled
from chuni_penguin.logging import logger
from chuni_penguin.ui.components import BannedEmbed

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


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

        if isinstance(exc, discord.NotFound):
            return

        embed, _ = await self._construct_error_embed(
            interaction,
            interaction.command.qualified_name if interaction.command else None,
            exc,
        )

        if embed.description is not None:
            with contextlib.suppress(discord.NotFound):
                if interaction.response.is_done():
                    await interaction.edit_original_response(embed=embed, view=None)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)

            return

        await logger.aexception(
            "Unhandled exception in app command",
            tag="app_command_error",
            command=interaction.command.qualified_name if interaction.command else None,
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

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

        await self._submit_error_to_webhook(interaction, exc)

        return

    @commands.Cog.listener()
    async def on_command_error(
        self,
        ctx: PenguinContext,
        error: commands.errors.CommandInvokeError,
    ):
        exc = error

        while hasattr(exc, "original"):
            exc = cast(Exception, exc.original)

        if isinstance(
            exc,
            (commands.CommandNotFound, app_commands.CommandNotFound, discord.NotFound),
        ):
            return

        embed, delete_after = await self._construct_error_embed(
            ctx,
            ctx.command.qualified_name if ctx.command else None,
            exc,
        )

        if embed.description is not None:
            await self._send_error(ctx, embed, delete_after=delete_after)
            return

        await logger.aexception(
            "Unhandled exception in command",
            tag="command_error",
            command=ctx.command.qualified_name if ctx.command else None,
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

        if config.bot.support_server_invite:
            embed.description += "\n"
            embed.description += (
                f"If this error keeps happening, please join the [support server]({config.bot.support_server_invite}) "
                "and report the bug in the #help-bugs channel!"
            )

        await self._send_error(ctx, embed)
        await self._submit_error_to_webhook(ctx, exc)

    async def _construct_error_embed(
        self,
        context_or_interaction: PenguinContext | discord.Interaction["ChuniBot"],
        command_name: str | None,
        exc: Exception,
    ):
        embed = discord.Embed(
            color=discord.Color.red(),
            title="Error",
        )
        delete_after: float | None = None

        # text_prefix is for the help command, since we don't have a slash help
        # command (yet)
        if isinstance((interaction := context_or_interaction), discord.Interaction) or (
            isinstance(context_or_interaction, Context)
            and (interaction := context_or_interaction.interaction) is not None
        ):
            if (guild_id := interaction.guild_id) is not None:
                text_prefix = interaction.client.prefixes.get(
                    guild_id, config.bot.default_prefix
                )
            else:
                text_prefix = config.bot.default_prefix

            prefix = "/"
        else:
            # The type checker is not smart enough to realize that the upper branch
            # already ensures that context_or_interaction cannot be an Interaction
            # down here.
            assert isinstance(context_or_interaction, Context)

            prefix = text_prefix = (
                context_or_interaction.clean_prefix or config.bot.default_prefix
            )

        match exc:
            # Network adapter errors
            case MaintenanceError():
                embed.description = "CHUNITHM-NET is currently undergoing maintenance. Please try again later."
            case ChuniNetError():
                if exc.code == ChuniNetError.RATE_LIMIT_EXCEEDED:
                    await logger.awarning(
                        "CHUNITHM-NET rate limit exceeded",
                        tag="chunithm_net_rate_limit_exceeded",
                        exc_info=exc,
                    )

                embed.description = f"CHUNITHM-NET error {exc.code}: {exc.description}"
            case NoCardsRegistered():
                embed.description = str(exc)
            case AuthenticationError():
                embed.description = (
                    f"The token has expired. Please log in again with `{prefix}login` in my DMs.\n"
                    "\n"
                    "To prevent being logged out constantly:\n"
                    "- Don't quickly switch between using the bot and visiting CHUNITHM-NET directly\n"
                    "- Log in using a separate incognito session\n"
                    "- Use SEGA ID instead of social media login (especially Twitter)"
                )
            case InvalidFriendCode():
                embed.description = "Could not find anyone with this friend code. Please double-check and try again."
            case HTTPError():
                if exc.text is not None:
                    displayed_error = f"`{exc.code} {exc.text}`"
                else:
                    displayed_error = f"`{exc.code}`"

                embed.description = f"An HTTP error occured while communicating with the network: {displayed_error}"

                if exc.code >= 500:
                    embed.description += "\nThis is likely not a problem with the bot."

                embed.set_image(url=f"https://http.cat/{exc.code}.jpg")
                embed.set_footer(text="Image from https://http.cat")
            case NetworkError():
                embed.description = (
                    "An error occurred while communicating with the network. Please try again later (or re-login).\n"
                    "\n"
                    "Detailed error:\n"
                    "```python\n"
                    f"{traceback.format_exception_only(exc)}\n"
                    "```"
                )

            # Discord HTTP errors
            case DiscordServerError():
                embed.description = "An error occured in Discord's servers. This is not a problem with the bot."

                embed.set_image(url=f"https://http.cat/{exc.code}.jpg")
                embed.set_footer(text="Image from https://http.cat")
            case discord.Forbidden():
                embed.description = "The bot is missing permissions to do something."
                await logger.awarning(
                    "missing permissions",
                    tag="missing_permissions",
                    command=command_name,
                    exc_info=exc,
                )

            # User input errors
            case commands.ExpectedClosingQuoteError():
                embed.description = "You're missing a quote somewhere. Perhaps you're using the wrong kind of quote (`\"` vs `”`)?"
            case commands.UnexpectedQuoteError():
                embed.description = (
                    f"Unexpected quote mark, {exc.quote!r}, in non-quoted string. If this was intentional, "
                    "escape the quote with a backslash (\\\\)."
                )
            case commands.InvalidEndOfQuotedStringError():
                embed.description = str(exc)
            case commands.RangeError():
                embed.description = (
                    str(exc)
                    + "\n"
                    + f"View help for this command with `{text_prefix}help {command_name}`."
                )

                if (
                    isinstance(context_or_interaction, Context)
                    and (parameter := context_or_interaction.current_parameter)
                    is not None
                ):
                    embed.description = embed.description.replace(
                        "value", f"`{parameter.displayed_name or parameter.name}`", 1
                    )
            case commands.BadLiteralArgument():
                to_string = [repr(x) for x in exc.literals]
                if len(to_string) > 2:
                    fmt = "{}, or {}".format(", ".join(to_string[:-1]), to_string[-1])
                else:
                    fmt = " or ".join(to_string)
                embed.description = (
                    f"`{exc.param.displayed_name or exc.param.name}` must be one of {fmt}, received {exc.argument!r}\n"
                    f"View help for this command with `{text_prefix}help {command_name}`."
                )
            case commands.BadArgument():
                embed.description = (
                    f"Bad argument: {exc!s}\n"
                    f"View help for this command with `{text_prefix}help {command_name}`."
                )
            case commands.MissingRequiredArgument():
                embed.description = (
                    f"Missing required argument: `{exc.param.displayed_name or exc.param.name}`\n"
                    f"View help for this command with `{text_prefix}help {command_name}`."
                )

            # Check failures
            case Banned():
                return BannedEmbed(
                    client=self.bot,
                    entry=exc.denylist,
                    server_name=exc.server_name,
                    support_server_invite=config.bot.support_server_invite,
                ), None
            case CommandDisabled():
                embed.description = str(exc)
                delete_after = 5
            case (
                commands.NotOwner()
                | commands.MissingPermissions()
                | app_commands.MissingPermissions()
            ):
                embed.description = "Insufficient permissions."
                delete_after = 5
            case (
                commands.BotMissingPermissions() | app_commands.BotMissingPermissions()
            ):
                missing = [
                    f"- {p.replace('_', ' ').replace('guild', 'server').title()}"
                    for p in exc.missing_permissions
                ]
                embed.description = (
                    f"I need the following permissions to run this command:\n"
                    f"{'\n'.join(missing)}\n"
                    "Please fix this and try again."
                )
            case commands.CheckFailure() | app_commands.CheckFailure():
                embed.description = "You are not allowed to use this command."
                delete_after = 5

            # Generic command errors
            case commands.CommandOnCooldown() | app_commands.CommandOnCooldown():
                embed.description = (
                    f"You're too fast. Take a break for {exc.retry_after:.2f} seconds."
                )
                delete_after = exc.retry_after
            case commands.ConversionError() | app_commands.TransformerError():
                await logger.aerror(
                    "unhandled conversion error",
                    tag="error_converter_transformer",
                    exc_info=exc,
                )
                embed.description = "One of the arguments provided cannot be parsed."
            case commands.CommandError() | app_commands.AppCommandError():
                embed.description = str(exc)

            # Non-Discord errors
            case songbird.SongbirdError():
                if (
                    context_or_interaction.guild is not None
                    and (voice := context_or_interaction.guild.voice_client) is not None
                ):
                    with contextlib.suppress(songbird.SongbirdError):
                        await voice.disconnect(force=True)

                await logger.aerror("voice error", tag="error_voice", exc_info=exc)
                embed.description = f"Voice error: {exc!s}"

            case (
                httpx.TimeoutException() | aiohttp.ServerTimeoutError() | TimeoutError()
            ):
                embed.description = "Timed out trying to connect to the network."
            case httpx.TransportError() | aiohttp.ClientConnectionError():
                embed.description = (
                    "An unknown network error occured trying to connect to the network.\n"
                    "\n"
                    "Detailed error:\n"
                    "```python\n"
                    f"{traceback.format_exception_only(exc)}\n"
                    "```"
                )

        return embed, delete_after

    async def _send_error(
        self,
        ctx: PenguinContext,
        embed: discord.Embed,
        *,
        delete_after: float | None = None,
    ):
        if isinstance(embed, BannedEmbed):
            with contextlib.suppress(discord.HTTPException):
                dm_channel = ctx.author.dm_channel

                if dm_channel is None:
                    dm_channel = await ctx.author.create_dm()

                if ctx.channel == dm_channel:
                    await ctx.reply(embed=embed)
                else:
                    await dm_channel.send(embed=embed)

            return

        is_thread = isinstance(ctx.channel, discord.Thread)

        if (
            ctx.interaction is not None
            or (not is_thread and ctx.bot_permissions.send_messages)
            or (is_thread and ctx.bot_permissions.send_messages_in_threads)
        ):
            with contextlib.suppress(discord.NotFound):
                if ctx.bot_permissions.embed_links:
                    await ctx.respond_or_edit(
                        embed=embed,
                        delete_after=delete_after,
                        view=None,
                        ephemeral=True,
                    )
                else:
                    await ctx.respond_or_edit(
                        embed.description,
                        delete_after=delete_after,
                        view=None,
                        ephemeral=True,
                    )
        else:
            with contextlib.suppress(discord.HTTPException):
                dm_channel = ctx.author.dm_channel

                if dm_channel is None:
                    dm_channel = await ctx.author.create_dm()

                await dm_channel.send(embed=embed)

    async def _submit_error_to_webhook(
        self,
        context_or_interaction: Context | discord.Interaction,
        exc: Exception,
    ):
        if (webhook_url := config.bot.error_reporting_webhook) is None:
            return

        command = context_or_interaction.command
        command_name = command.qualified_name if command else None

        files = [
            discord.File(
                io.BytesIO("".join(traceback.format_exception(exc)).encode()),
                "traceback.txt",
            )
        ]

        if isinstance(context_or_interaction, discord.Interaction):
            content = (
                f"Unhandled exception in `/{command_name}`\n"
                "\n"
                f"User ID: `{context_or_interaction.user.id}` ({context_or_interaction.user.mention})\n"
                f"Channel ID: `{context_or_interaction.channel.id if context_or_interaction.channel else None}`{f' (<#{context_or_interaction.channel.id}>)' if context_or_interaction.channel else ''}\n"
                f"Guild ID: `{context_or_interaction.guild.id if context_or_interaction.guild else None}`{f' ({context_or_interaction.guild.name})' if context_or_interaction.guild else ''}"
            )
            files.append(
                discord.File(
                    io.BytesIO(
                        json.dumps(
                            context_or_interaction.data,
                            ensure_ascii=False,
                            indent=4,
                        ).encode()
                    ),
                    "interaction_data.json",
                )
            )
        else:
            args = context_or_interaction.args
            ctx_arg_idx = None

            for i, arg in enumerate(args):
                if isinstance(arg, Context):
                    ctx_arg_idx = i
                    break

            if ctx_arg_idx is not None:
                args = args[ctx_arg_idx + 1 :]

            content = (
                f"Unhandled exception in `{context_or_interaction.clean_prefix}{command_name}`\n"
                "\n"
                f"User ID: `{context_or_interaction.author.id}` ({context_or_interaction.author.mention})\n"
                f"Channel ID: `{context_or_interaction.channel.id}` (<#{context_or_interaction.channel.id}>)\n"
                f"Guild ID: `{context_or_interaction.guild.id if context_or_interaction.guild else None}`{f' ({context_or_interaction.guild.name})' if context_or_interaction.guild else ''}\n"
                "\n"
                "Arguments:\n"
                "```python\n"
                f"{pformat(args, sort_dicts=False, underscore_numbers=True)}\n"
                "```\n"
                "\n"
                "Keyword arguments:\n"
                "```python\n"
                f"{pformat(context_or_interaction.kwargs, sort_dicts=False, underscore_numbers=True)}\n"
                "```"
            )

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(webhook_url, session=session)
            client_user = cast(discord.ClientUser, self.bot.user)

            await webhook.send(
                username=client_user.display_name,
                avatar_url=client_user.display_avatar.url,
                content=content,
                allowed_mentions=discord.AllowedMentions.none(),
                files=files,
            )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(EventsCog(bot))
