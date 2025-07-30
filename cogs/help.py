import re
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, override

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Command, Group

from utils.config import config

if TYPE_CHECKING:
    from bot import ChuniBot

MENTION_PREFIX_RE = re.compile(r"<@[!&]?\d+>")


class HelpCommand(commands.HelpCommand):
    COLOUR = discord.Colour.yellow()

    @property
    def prefix(self):
        return self.context.clean_prefix

    @override
    async def send_error_message(self, error: str, /) -> None:
        await self.context.reply(
            embed=discord.Embed(
                color=discord.Color.red(),
                title="Error",
                description=error,
            ),
            mention_author=False,
        )

    async def send_bot_help(
        self, mapping: Mapping[Optional[Cog], List[Command[Any, ..., Any]]], /
    ) -> None:
        ctx = self.context
        bot = ctx.bot

        assert bot.user is not None

        footer_items = [
            f"Use {self.prefix}help <command> for more info on a command.",
            "Source code: https://github.com/beer-psi/chuni-penguin",
        ]

        if config.bot.support_server_invite is not None:
            footer_items[1] = (
                f"Discord: {config.bot.support_server_invite} | Source code: https://github.com/beer-psi/chuni-penguin"
            )

        embed = (
            discord.Embed(color=self.COLOUR)
            # bot.user already exists if this command is invoked
            .set_author(
                name=f"Command list for {bot.user.display_name}:",
                icon_url=bot.user.avatar.url if bot.user.avatar else None,
            )
            .set_footer(  # type: ignore[reportGeneralTypeIssues]
                text="\n".join(footer_items),
            )
        )
        description_parts: list[str] = []

        for cogs, cmd in mapping.items():
            name = "No category" if cogs is None else cogs.qualified_name
            filtered = await self.filter_commands(cmd, sort=True)
            if filtered:
                description_parts.append(f"**{name}** - ")

                for c in filtered:
                    description_parts.append(f"`{c.name}`")
                    description_parts.append(" ")

                description_parts.append("\n")

        embed.description = "".join(description_parts)

        await ctx.reply(embed=embed, mention_author=False)

    async def send_command_help(self, command: Command[Any, ..., Any], /) -> None:
        embed = discord.Embed(color=self.COLOUR)
        description_parts: list[str] = [
            f"```{self.prefix}{command.qualified_name} {command.signature}```"
        ]

        if command.help is not None:
            description_parts.append(f"\n{command.help}\n")

        params = command.clean_params.values()

        if params:
            params_desc_parts: list[str] = []
            for param in params:
                if not param.description:
                    continue

                params_desc_parts.append(f"`{param.name}`: {param.description}")

                if param.default is not param.empty:
                    params_desc_parts.append(f" (default: {param.default})")

                params_desc_parts.append("\n")

            if params_desc_parts:
                description_parts.append(
                    f"\n**Parameters:**\n{''.join(params_desc_parts)}"
                )

        embed.description = "".join(description_parts)

        await self.context.reply(embed=embed, mention_author=False)

    @override
    async def send_group_help(self, group: Group[Any, ..., Any], /) -> None:
        embed = discord.Embed(color=self.COLOUR)
        embed = discord.Embed(color=self.COLOUR)
        description_parts: list[str] = [
            f"```{self.prefix}{group.qualified_name} {group.signature}```"
        ]

        if group.help is not None:
            description_parts.append(f"\n{group.help}\n")

        params = group.clean_params.values()

        if params:
            params_desc_parts: list[str] = []
            for param in params:
                if not param.description:
                    continue

                params_desc_parts.append(f"`{param.name}`: {param.description}")

                if param.default is not param.empty:
                    params_desc_parts.append(f" (default: {param.default})")

                params_desc_parts.append("\n")

            if params_desc_parts:
                description_parts.append(
                    f"\n**Parameters:**\n{''.join(params_desc_parts)}\n"
                )

        if len(group.commands) > 0:
            commands = await self.filter_commands(group.commands, sort=True)

            description_parts.append("\n**Commands:**\n")

            for command in commands:
                description_parts.append(
                    f"`{self.context.clean_prefix}{command.qualified_name}`"
                )

                if command.short_doc:
                    description_parts.append(f": {command.short_doc}")

                description_parts.append("\n")

        embed.description = "".join(description_parts)

        await self.context.reply(embed=embed, mention_author=False)


async def setup(bot: "ChuniBot"):
    bot.help_command = HelpCommand()
