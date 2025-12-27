import contextlib
import io
from asyncio import TimeoutError
from http.cookiejar import Cookie as HTTPCookie
from http.cookiejar import LWPCookieJar
from secrets import SystemRandom
from typing import TYPE_CHECKING, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import update

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.database import Cookie
from chuni_penguin.logging import logged_app_command, logged_prefix_command, logger
from chuni_penguin.networks.chunithm_net import ChunithmNet, is_valid_clal
from chuni_penguin.networks.errors import AuthenticationError, NetworkError
from chuni_penguin.ui import LoginFlowView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class AuthCog(commands.Cog, name="Auth"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils
        self.random = SystemRandom()

    @commands.hybrid_command(name="logout", extras={"invoke_on_edit": False})
    @logged_prefix_command
    async def logout(self, ctx: PenguinContext, *, invalidate: bool = False):
        """Logs you out of the bot.

        Parameters
        ----------
        invalidate: bool
            Signs out from CHUNITHM-NET, making the token unusable.
        """
        msg = "Successfully logged out."

        if invalidate:
            logged_out = False

            with contextlib.suppress(AuthenticationError):
                async with ctx.bot.chunithm_networks.network(
                    ctx, ctx.author.id, chunithm_net=True
                ) as client:
                    await client.logout()
                    logged_out = True

            if not logged_out:
                await logger.awarning(
                    "Could not sign user out of CHUNITHM-NET",
                    tag="chunithm_net_logout_failed",
                    user_id=ctx.author.id,
                )
                msg = (
                    "There was an error signing out from CHUNITHM-NET. "
                    "However, your account has been deleted from our records."
                )

        async with ctx.typing(), self.bot.begin_db_session() as session:
            stmt = (
                update(Cookie)
                .where(Cookie.discord_id == ctx.author.id)
                .values(cookie="")
            )
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
        raw_jar = f"#LWP-Cookies-2.0\n{jar.as_lwp_str()}"

        async with ChunithmNet(raw_jar) as client:
            try:
                await client.get_minimal_profile()
            except NetworkError as e:
                return e

        async with self.bot.begin_db_session() as session, session.begin():
            await session.merge(Cookie(discord_id=id, cookie=client.authentication))
            return None

    @commands.hybrid_command("login")
    @logged_prefix_command
    async def login(self, ctx: PenguinContext, clal: Optional[str] = None):
        """Link with your CHUNITHM-NET account.

        You must enable direct messages with the bot. Alternatively, use the slash
        command variant, `/login`.

        Parameters
        ----------
        clal: Optional[str]
            IGNORE IF YOU DON'T KNOW WHAT THIS IS FOR. You will get instructions on how to log in.
        """

        if ctx.interaction is not None and ctx.guild is not None:
            await ctx.interaction.response.defer(ephemeral=True, thinking=True)

        channel = ctx.channel

        await logger.adebug(
            "Received login request",
            tag="login_request_received",
            user_id=ctx.author.id,
            user_name=ctx.author.name,
        )

        # if message in guild and is text command
        if ctx.guild is not None and ctx.interaction is None:
            please_delete_message = ""

            if clal is not None:
                try:
                    await logger.adebug(
                        "Attempting to delete message for containing a token",
                        tag="attempt_delete_message_exposing_keys",
                        guild_id=ctx.guild.id if ctx.guild else None,
                        channel_id=ctx.channel.id,
                        user_id=ctx.author.id,
                        message_id=ctx.message.id,
                    )

                    await ctx.message.delete()
                except discord.errors.HTTPException:
                    await logger.awarning(
                        "Could not delete message with token exposed",
                        tag="failed_delete_message_exposing_keys",
                        guild_id=ctx.guild.id if ctx.guild else None,
                        channel_id=ctx.channel.id,
                        user_id=ctx.author.id,
                        message_id=ctx.message.id,
                    )

                    please_delete_message = (
                        "You sent the command in a public channel and included your "
                        "CHUNITHM-NET cookie, which leaves your CHUNITHM-NET account at risk. "
                        "Please delete the command yourself, as I do not have sufficient "
                        "permissions to do it. "
                        "Please also practice some internet safety and don't send credentials "
                        "in public places.\n\n"
                        "Visit https://chunithm-net-eng.com/mobile/home/userOption/logout/ "
                        "on the tab you retrieved the cookie from to revoke the cookie."
                    )

            await logger.adebug(
                "Sending login instructions",
                tag="send_login_instructions",
                user_id=ctx.author.id,
            )

            channel = (
                ctx.author.dm_channel
                if ctx.author.dm_channel
                else await ctx.author.create_dm()
            )

            await ctx.respond_or_edit(
                "Login instructions have been sent to your DMs. "
                f"(please **enable Privacy Settings -> Direct Messages** if you haven't received it.)\n\n{please_delete_message}"
            )
        elif clal is not None and is_valid_clal(clal):
            if (e := await self._verify_and_login(ctx.author.id, clal)) is None:
                await logger.adebug(
                    "User logged in.", tag="user_logged_in", user_id=ctx.author.id
                )

                return await ctx.respond_or_edit(
                    embed=discord.Embed(
                        color=discord.Color.green(),
                        title="Successfully logged in",
                        description="You can now use the bot's CHUNITHM-NET commands.",
                    ),
                )

            await logger.adebug(
                "Invalid token provided.",
                tag="user_invalid_token_provided",
                user_id=ctx.author.id,
            )

            msg = f"Invalid cookie: {e.__class__.__name__}: {e}"
            raise commands.CommandError(msg)

        passcode = str(self.random.randrange(10**5, 10**6))
        view = LoginFlowView(ctx, passcode, config.web.base_url)

        await logger.adebug(
            "Initiating login flow",
            tag="login_flow_start",
            user_id=ctx.author.id,
        )

        if ctx.channel == channel or ctx.interaction is not None:
            msg = await view.start(
                content=f"If you're trying to link your Kamaitachi account, use `{ctx.clean_prefix}kamaitachi link` instead!",
            )
        else:
            try:
                msg = await view.start_in(
                    channel,
                    content=f"If you're trying to link your Kamaitachi account, use `{ctx.clean_prefix}kamaitachi link` instead!",
                )
            except discord.errors.Forbidden:
                await logger.awarning(
                    "could not send login instructions",
                    tag="error_dm_login",
                    user_id=ctx.author.id,
                )
                return None

        try:
            clal = await self.bot.wait_for(f"chunithm_login_{passcode}", timeout=300)

            if (e := await self._verify_and_login(ctx.author.id, clal)) is None:  # type: ignore[reportGeneralTypeIssues]
                await logger.adebug(
                    "User logged in.", tag="user_logged_in", user_id=ctx.author.id
                )

                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        color=discord.Color.green(),
                        title="Successfully logged in",
                        description="You can now use the bot's CHUNITHM-NET commands.",
                    ),
                    view=None,
                )
            else:
                await logger.adebug(
                    "Invalid token provided.",
                    tag="user_invalid_token_provided",
                    user_id=ctx.author.id,
                )

                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        title="Failed to login",
                        description=f"Invalid cookie: {e.__class__.__name__}: {e}",
                    ),
                    view=None,
                )
        except TimeoutError:
            await logger.awarning(
                "Login flow timed out.", tag="login_flow_timeout", user_id=ctx.author.id
            )

            await msg.edit(
                content=None,
                embed=discord.Embed(
                    color=discord.Color.yellow(),
                    title="Login session timed out",
                    description=f"Please use `{'/' if ctx.interaction else config.bot.default_prefix}login` to restart the login process.",
                ),
                view=None,
            )

    @commands.command("token")
    @commands.dm_only()
    @logged_prefix_command
    async def token(self, ctx: Context):
        """Show your current token.

        Useful for logging into other bots, but DO NOT show it to other people.
        """

        async with ctx.typing():
            raw_jar = await self.utils.login_check(ctx.author.id)
            jar = LWPCookieJar()
            jar._really_load(  # pyright: ignore[reportAttributeAccessIssue]
                io.StringIO(raw_jar), "?", ignore_discard=False, ignore_expires=False
            )

            for cookie in jar:
                if (
                    cookie.name == "clal"
                    and cookie.domain == "lng-tgk-aime-gw.am-all.net"
                ):
                    await ctx.reply(
                        f"Your token: ||{cookie.value}|| (click to reveal, DO NOT show to other people.)",
                        mention_author=False,
                    )
                    return

        msg = "Could not find your token. This is probably a bug."
        raise commands.CommandError(msg)

    @app_commands.command(name="token", description="Show your current token.")
    @logged_app_command
    async def token_slash(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        raw_jar = await self.utils.login_check(interaction.user.id)
        jar = LWPCookieJar()
        jar._really_load(  # pyright: ignore[reportAttributeAccessIssue]
            io.StringIO(raw_jar), "?", ignore_discard=False, ignore_expires=False
        )

        for cookie in jar:
            if cookie.name == "clal" and cookie.domain == "lng-tgk-aime-gw.am-all.net":
                await interaction.followup.send(
                    content=f"Your token: ||{cookie.value}|| (click to reveal, DO NOT show to other people.)"
                )
                return

        msg = "Could not find your token. This is probably a bug."
        raise app_commands.AppCommandError(msg)


async def setup(bot: "ChuniBot") -> None:
    await bot.add_cog(AuthCog(bot))
