from asyncio import TimeoutError
from secrets import SystemRandom
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import delete

from chunithm_net import ChuniNet
from database.models import Cookie
from utils.views.login import LoginFlowView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.botutils import UtilsCog


class AuthCog(commands.Cog, name="Auth"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore
        self.random = SystemRandom()

    @commands.hybrid_command(
        name="logout",
        description="Logs you out of the bot.",
    )
    async def logout(self, ctx: Context):
        async with ctx.typing(), self.bot.begin_db_session() as session:
            stmt = delete(Cookie).where(Cookie.discord_id == ctx.author.id)
            await session.execute(stmt)
        await ctx.reply("Successfully logged out.", mention_author=False)

    async def _verify_and_login(self, id: int, clal: str) -> Optional[Exception]:
        if clal.startswith("clal="):
            clal = clal[5:]

        async with ChuniNet(clal) as client:
            try:
                await client.validate_cookie()

                async with self.bot.begin_db_session() as session, session.begin():
                    await session.merge(Cookie(discord_id=id, cookie=clal))
            except Exception as e:
                return e

    @commands.hybrid_command("login")
    async def login(self, ctx: Context, clal: Optional[str] = None):
        """Link with your CHUNITHM-NET account.

        Parameters
        ----------
        clal: str
            The `clal` cookie from CHUNITHM-NET. Run this command without arguments to get instructions.
        """

        channel = ctx.channel

        if not isinstance(ctx.channel, discord.channel.DMChannel):
            please_delete_message = ""
            if clal is not None:
                try:
                    await ctx.message.delete()
                except discord.errors.Forbidden:
                    please_delete_message = "Please delete the original command, as people can use the cookie to access your CHUNITHM-NET profile."

            channel = (
                ctx.author.dm_channel
                if ctx.author.dm_channel
                else await ctx.author.create_dm()
            )

            await ctx.send(
                f"Login instructions have been sent to your DMs. {please_delete_message}"
                "(please **enable Privacy Settings -> Direct Messages** if you haven't received it.)"
            )

        if clal is not None:
            if (e := await self._verify_and_login(ctx.author.id, clal)) is None:
                return await channel.send("Successfully logged in.")
            else:
                raise commands.BadArgument(f"Invalid cookie: {e}")

        passcode = (
            str(self.random.randrange(10**5, 10**6))
            if self.bot.app is not None
            else None
        )
        view = LoginFlowView(ctx, passcode)
        embed = view.format_embed(view.items[0])
        if ctx.channel == channel:
            msg = view.message = await ctx.reply(
                embed=embed, view=view, mention_author=False
            )
        else:
            try:
                msg = view.message = await channel.send(embed=embed, view=view)
            except discord.errors.Forbidden:
                return

        if self.bot.app is None:
            return

        try:
            clal = await self.bot.wait_for(f"chunithm_login_{passcode}", timeout=300)
            if (e := await self._verify_and_login(ctx.author.id, clal)) is None:  # type: ignore
                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title="Successfully logged in",
                        description="You can now use the bot's CHUNITHM-NET commands.",
                    ),
                )
            else:
                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title="Failed to login",
                        description=f"Invalid cookie: {e}",
                    ),
                )
        except TimeoutError:
            await msg.edit(
                content=None,
                embed=discord.Embed(
                    title="Login session timed out",
                    description="Please use `c>login` to restart the login process.",
                ),
            )


async def setup(bot: "ChuniBot") -> None:
    await bot.add_cog(AuthCog(bot))
