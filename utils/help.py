from typing import Any, List, Mapping, Optional

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Command, when_mentioned


class HelpCommand(commands.HelpCommand):
    COLOUR = discord.Colour.yellow()

    async def send_bot_help(
        self, mapping: Mapping[Optional[Cog], List[Command[Any, ..., Any]]], /
    ) -> None:
        ctx = self.context
        bot = ctx.bot

        assert bot.user is not None

        prefix = next(
            iter(
                set(await bot.get_prefix(ctx.message))
                - set(when_mentioned(bot, ctx.message))
            )
        )

        embed = (
            discord.Embed(color=self.COLOUR)
            # bot.user already exists if this command is invoked
            .set_author(
                name=f"Command list for {bot.user.display_name}:",
                icon_url=bot.user.avatar.url if bot.user.avatar else None,
            )
            .set_footer(  # type: ignore[reportGeneralTypeIssues]
                text=f"Use {prefix}help <command> for more info on a command.\nSource code: https://github.com/beer-psi/chuni-penguin"
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
        ctx = self.context
        bot = ctx.bot

        prefix = next(
            iter(
                set(await bot.get_prefix(ctx.message))
                - set(when_mentioned(bot, ctx.message))
            )
        )

        embed = discord.Embed(color=self.COLOUR)
        embed.description = f"```{prefix}{command.qualified_name}```\n{command.help}"

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
