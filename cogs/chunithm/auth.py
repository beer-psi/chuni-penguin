from asyncio import TimeoutError
from http.cookiejar import Cookie as HTTPCookie
from http.cookiejar import LWPCookieJar
from secrets import SystemRandom
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import delete

from chunithm_net import ChuniNet
from chunithm_net.exceptions import ChuniNetException, InvalidTokenException
from database.models import Cookie
from utils import asuppress
from utils.config import config
from utils.logging import logger as root_logger
from utils.views.login import LoginFlowView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.botutils import UtilsCog

logger = root_logger.getChild(__name__)


class AuthCog(commands.Cog, name="Auth"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]
        self.random = SystemRandom()

    @commands.hybrid_command(name="logout")
    async def logout(self, ctx: Context, *, invalidate: bool = False):
        """Logs you out of the bot.

        Parameters
        ----------
        invalidate: bool
            Signs out from CHUNITHM-NET, making the token unusable.
        """
        msg = "Successfully logged out."

        if invalidate:
            async with asuppress(InvalidTokenException), self.utils.chuninet(
                ctx
            ) as client:
                result = await client.logout()

                if not result:
                    logger.warning(
                        "Could not sign user %d out of CHUNITHM-NET.", ctx.author.id
                    )
                    msg = (
                        "There was an error signing out from CHUNITHM-NET. "
                        "However, your account has been deleted from our records."
                    )

        async with ctx.typing(), self.bot.begin_db_session() as session:
            stmt = delete(Cookie).where(Cookie.discord_id == ctx.author.id)
            await session.execute(stmt)
            await session.commit()
        await ctx.reply(msg, mention_author=False)

    async def _verify_and_login(self, id: int, clal: str) -> Optional[Exception]:
        if clal.startswith("clal="):
            clal = clal[5:]

        cookie = HTTPCookie(
            version=0,
            name="clal",
            value=clal,
            port=None,
            port_specified=False,
            domain="lng-tgk-aime-gw.am-all.net",
            domain_specified=True,
            domain_initial_dot=False,
            path="/common_auth",
            path_specified=True,
            secure=False,
            expires=3856586927,  # 2092-03-17 10:08:47Z
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
        )
        jar = LWPCookieJar()
        jar.set_cookie(cookie)

        async with ChuniNet(jar) as client:
            try:
                await client.authenticate()
            except ChuniNetException as e:
                return e

        async with self.bot.begin_db_session() as session, session.begin():
            await session.merge(
                Cookie(discord_id=id, cookie=f"#LWP-Cookies-2.0\n{jar.as_lwp_str()}")
            )
            return None

    @commands.hybrid_command("login")
    async def login(self, ctx: Context, clal: Optional[str] = None):
        """Link with your CHUNITHM-NET account.

        Parameters
        ----------
        clal: str
            The `clal` cookie from CHUNITHM-NET. Run this command without arguments to get instructions.
        """

        channel = ctx.channel

        logger.debug(
            "Received login request from username %s (%d)",
            ctx.author.name,
            ctx.author.id,
        )

        if not isinstance(ctx.channel, discord.channel.DMChannel):
            please_delete_message = ""

            if clal is not None:
                try:
                    logger.debug(
                        "Deleting message %d (guild %d) because it contains a token",
                        ctx.message.id,
                        -1 if ctx.guild is None else ctx.guild.id,
                    )
                    await ctx.message.delete()
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    logger.warning(
                        "Could not delete message %d (guild %d) with token sent in public channel",
                        ctx.message.id,
                        -1 if ctx.guild is None else ctx.guild.id,
                    )
                    please_delete_message = "Please delete the original command, as people can use the cookie to access your CHUNITHM-NET profile."

            logger.debug("Sending login instructions to user %d", ctx.author.id)

            channel = (
                ctx.author.dm_channel
                if ctx.author.dm_channel
                else await ctx.author.create_dm()
            )

            await ctx.send(
                f"Login instructions have been sent to your DMs. {please_delete_message}"
                "(please **enable Privacy Settings -> Direct Messages** if you haven't received it.)"
            )
        elif clal is not None:
            if await self._verify_and_login(ctx.author.id, clal) is None:
                logger.debug("User %d logged in.", ctx.author.id)

                return await channel.send("Successfully logged in.")

            logger.debug("Invalid token provided.")

            msg = "Invalid cookie."
            raise commands.BadArgument(msg)

        passcode = (
            str(self.random.randrange(10**5, 10**6))
            if self.bot.app is not None
            else None
        )
        view = LoginFlowView(ctx, passcode, config.web.base_url)
        embed = view.format_embed(view.items[0])

        logger.debug("Initiating login flow for user %d", ctx.author.id)

        if ctx.channel == channel:
            msg = view.message = await ctx.reply(
                content=f"If you're trying to link your Kamaitachi account, use `{ctx.prefix}kamaitachi link` instead!",
                embed=embed,
                view=view,
                mention_author=False,
            )
        else:
            try:
                msg = view.message = await channel.send(
                    content=f"If you're trying to link your Kamaitachi account, use `{ctx.prefix}kamaitachi link` instead!",
                    embed=embed,
                    view=view,
                )
            except discord.errors.Forbidden:
                return None

        if self.bot.app is None:
            return None

        try:
            clal = await self.bot.wait_for(f"chunithm_login_{passcode}", timeout=300)

            if await self._verify_and_login(ctx.author.id, clal) is None:  # type: ignore[reportGeneralTypeIssues]
                logger.debug("User %d logged in.", ctx.author.id)

                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title="Successfully logged in",
                        description="You can now use the bot's CHUNITHM-NET commands.",
                    ),
                )
            else:
                logger.debug("Invalid token provided.")

                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title="Failed to login",
                        description="Invalid cookie.",
                    ),
                )
        except TimeoutError:
            logger.warning("Login flow timed out.")

            await msg.edit(
                content=None,
                embed=discord.Embed(
                    title="Login session timed out",
                    description="Please use `c>login` to restart the login process.",
                ),
            )

    @commands.command("token")
    @commands.dm_only()
    async def token(self, ctx: Context):
        """Show your current token.

        Useful for logging into other bots, but DO NOT show it to other people.
        """

        async with ctx.typing():
            jar = await self.utils.login_check(ctx)
    
            for cookie in jar:
                if cookie.name == "clal" and cookie.domain == "lng-tgk-aime-gw.am-all.net":
                    await ctx.reply(
                        f"Your token: ||{cookie.value}|| (click to reveal, DO NOT show to other people.)"
                    )
                    return

        msg = "Could not find your token. This is probably a bug."
        raise commands.CommandError(msg)

    @app_commands.command(name="token", description="Show your current token.")
    async def token_slash(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        jar = await self.utils.login_check(ctx)

        for cookie in jar:
            if cookie.name == "clal" and cookie.domain == "lng-tgk-aime-gw.am-all.net":
                await interaction.response.edit_message(
                    content=f"Your token: ||{cookie.value}|| (click to reveal, DO NOT show to other people.)"
                )
                return

        msg = "Could not find your token. This is probably a bug."
        raise app_commands.AppCommandError(msg)


async def setup(bot: "ChuniBot") -> None:
    await bot.add_cog(AuthCog(bot))
