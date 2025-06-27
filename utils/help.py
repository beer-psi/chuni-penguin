import re
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, cast, override

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
        prefix = self.context.prefix

        if prefix is None or MENTION_PREFIX_RE.match(prefix):
            if (guild := self.context.guild) is not None:
                return cast("ChuniBot", self.context.bot).prefixes.get(
                    guild.id, config.bot.default_prefix
                )
            return config.bot.default_prefix

        return prefix

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
        description = ""
        for cogs, cmd in mapping.items():
            name = "No category" if cogs is None else cogs.qualified_name
            filtered = await self.filter_commands(cmd, sort=True)
            if filtered:
                description += f"**{name}** - "
                description += " ".join([f"`{c.name}`" for c in filtered])
                description += "\n"
        embed.description = description
        await self.get_destination().send(embed=embed)

        return await super().send_bot_help(mapping)

    async def send_command_help(self, command: Command[Any, ..., Any], /) -> None:
        embed = discord.Embed(color=self.COLOUR)
        embed.description = (
            f"```{self.prefix}{command.qualified_name}```\n{command.help}"
        )

        params = command.clean_params.values()
        if params:
            params_desc = ""
            for param in params:
                if not param.description:
                    continue

                params_desc += f"`{param.name}`"
                params_desc += f": {param.description}"
                if param.default is not param.empty:
                    params_desc += f" (default: {param.default})"

                params_desc += "\n"

            if params_desc:
                embed.description += f"\n\n**Parameters:**\n{params_desc}"
        await self.get_destination().send(embed=embed)

    @override
    async def send_group_help(self, group: Group[Any, ..., Any], /) -> None:
        embed = discord.Embed(color=self.COLOUR)
        embed.description = f"```{self.prefix}{group.qualified_name}```\n{group.help}"

        params = group.clean_params.values()
        if params:
            params_desc = ""
            for param in params:
                if not param.description:
                    continue

                params_desc += f"`{param.name}`"
                params_desc += f": {param.description}"
                if param.default is not param.empty:
                    params_desc += f" (default: {param.default})"

                params_desc += "\n"

            if params_desc:
                embed.description += f"\n\n**Parameters:**\n{params_desc}"
        await self.get_destination().send(embed=embed)
