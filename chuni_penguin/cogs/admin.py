import asyncio
import contextlib
from typing import TYPE_CHECKING, Literal, Optional

import discord
from discord.ext import commands

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class AdminCog(commands.Cog, name="Admin", command_attrs={"hidden": True}):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

    @commands.command("treesync")
    @commands.is_owner()
    async def sync(
        self,
        ctx: PenguinContext,
        guilds: commands.Greedy[discord.Object],
        spec: Optional[Literal["~", "*", "^"]] = None,
    ) -> None:
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                if ctx.guild is None:
                    raise commands.NoPrivateMessage

                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.respond_or_edit(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.respond_or_edit(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command("say", extras={"invoke_on_edit": False})
    @commands.is_owner()
    async def say(
        self,
        ctx: PenguinContext,
        target: discord.TextChannel
        | discord.VoiceChannel
        | discord.StageChannel
        | discord.Thread
        | discord.User,
        *,
        content: str,
    ):
        """Say stuff as the bot."""

        if (reference := await ctx.resolve_message_reference()) is not None:
            await reference.reply(content=content, mention_author=False)
        else:
            await target.send(content=content)

        if ctx.bot_permissions.manage_messages:
            with contextlib.suppress(discord.HTTPException):
                await ctx.message.delete()

    @commands.group("botconfig")
    @commands.is_owner()
    async def botconfig(self, ctx: PenguinContext):
        pass

    @botconfig.command("reload")
    @commands.is_owner()
    async def botconfig_reload(self, ctx: PenguinContext):
        await asyncio.to_thread(config.reload)
        await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")


async def setup(bot: "ChuniBot"):
    await bot.add_cog(AdminCog(bot))
