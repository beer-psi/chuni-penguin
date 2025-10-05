from typing import TYPE_CHECKING, Literal, Optional

import discord
from discord.ext import commands
from sqlalchemy import delete

from chuni_penguin.context import PenguinContext
from chuni_penguin.database import Denylist

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

    @commands.command("block")
    @commands.is_owner()
    async def block(
        self, ctx: PenguinContext, objects: commands.Greedy[discord.Object]
    ):
        """Blocks users or guilds from using the bot globally."""

        async with self.bot.begin_db_session() as session:
            for object in objects:
                session.add(Denylist(object_id=object.id))
                self.bot.denylist.add(object.id)

            await session.commit()

        await ctx.message.add_reaction("✅")

    @commands.command("unblock")
    @commands.is_owner()
    async def unblock(
        self, ctx: PenguinContext, objects: commands.Greedy[discord.Object]
    ):
        """Unblocks users or guilds from using the bot globally."""

        async with self.bot.begin_db_session() as session:
            query = delete(Denylist).where(
                Denylist.object_id.in_([object.id for object in objects])
            )

            await session.execute(query)
            await session.commit()

        for object in objects:
            self.bot.denylist.discard(object.id)

        await ctx.message.add_reaction("✅")


async def setup(bot: "ChuniBot"):
    await bot.add_cog(AdminCog(bot))
