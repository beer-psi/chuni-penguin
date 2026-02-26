import itertools
import re
from typing import TYPE_CHECKING, Any, List, Mapping, Optional, override

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Cog, Command, Group, GroupMixin
from discord.ext.commands.core import hooked_wrapped_callback
from rapidfuzz import fuzz, process

from chuni_penguin.config import config
from chuni_penguin.constants import SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot

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
            description_parts.append(
                f"\n{command.help.replace('$PREFIX', self.context.clean_prefix)}\n"
            )

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
            description_parts.append(
                f"\n{group.help.replace('$PREFIX', self.context.clean_prefix)}\n"
            )

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


async def help_command_autocomplete(
    interaction: discord.Interaction["ChuniBot"], current: str
) -> list[app_commands.Choice[str]]:
    commands = itertools.chain(
        *[cog.get_commands() for cog in interaction.client.cogs.values()]
    )
    command_names = [c.qualified_name for c in commands if not c.hidden]

    if len(current) < 2:
        return [app_commands.Choice(name=c, value=c) for c in command_names[:25]]

    if (command := interaction.client.get_command(current)) is not None:
        choices = [
            app_commands.Choice(
                name=command.qualified_name, value=command.qualified_name
            )
        ]

        if isinstance(command, GroupMixin):
            choices.extend(
                app_commands.Choice(name=c.qualified_name, value=c.qualified_name)
                for c in command.commands
            )

        if len(choices) > 25:
            choices = choices[:25]

        return choices

    results = process.extract(
        current,
        command_names,
        scorer=fuzz.QRatio,
        limit=50,
        score_cutoff=SIMILARITY_THRESHOLD,
    )

    return [app_commands.Choice(name=c, value=c) for c, _, _ in results[:25]]


@app_commands.command(
    name="help",
    description="Display the list of commands, or help for a specific command.",
)
@app_commands.describe(command="The command to show help for.")
@app_commands.autocomplete(command=help_command_autocomplete)
async def help_slash(
    interaction: discord.Interaction["ChuniBot"], command: str | None = None
):
    if (help_command := interaction.client.help_command) is None:
        await interaction.response.send_message(
            content="An internal error has occured.", ephemeral=True
        )
        return

    interaction._baton = ctx = await interaction.client.get_context(interaction)
    help_command = help_command.copy()
    help_command.context = ctx
    injected = hooked_wrapped_callback(
        help_command._command_impl, ctx, help_command.command_callback
    )

    try:
        await injected(ctx, command=command)
    except commands.errors.CommandError as e:
        await help_command._command_impl.dispatch_error(ctx, e)


async def setup(bot: "ChuniBot"):
    bot.help_command = HelpCommand()
    bot.tree.add_command(help_slash)


async def teardown(bot: "ChuniBot"):
    bot.tree.remove_command("help")
