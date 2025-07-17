from http.cookiejar import CookieJar
from typing import TYPE_CHECKING, Any, override

import discord.ui
import httpx
from discord import Interaction
from discord.abc import MISSING
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chunithm_net import _AUTHENTICATION_URL
from utils.logging import logger

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from bot import ChuniBot


class SegaIDLoginModal(discord.ui.Modal, title="Login with SEGA ID"):
    username = discord.ui.TextInput(label="SEGA ID Username", min_length=1)
    password = discord.ui.TextInput(label="SEGA ID Password", min_length=1)

    def __init__(
        self,
        code: str,
        *,
        title: str = MISSING,
        timeout: float | None = None,
        custom_id: str = MISSING,
    ) -> None:
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)

        self.code = code

    @override
    async def on_submit(self, interaction: Interaction["ChuniBot"]) -> None:
        await interaction.response.defer(ephemeral=True)

        jar = CookieJar()

        async with httpx.AsyncClient(
            cookies=jar,
            timeout=httpx.Timeout(timeout=60.0),
            transport=httpx.AsyncHTTPTransport(retries=5),
        ) as client:
            await client.get(_AUTHENTICATION_URL)

            resp = await client.post(
                "https://lng-tgk-aime-gw.am-all.net/common_auth/login/sid/",
                data={
                    "retention": "1",
                    "sid": self.username.value,
                    "password": self.password.value,
                },
                follow_redirects=False,
            )

            if (
                location := resp.headers.get("location")
            ) is None or "https://chunithm-net-eng.com" not in location:
                await interaction.followup.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        title="Error",
                        description="Invalid username or password.",
                    ),
                    ephemeral=True,
                )
                return
            clal = client.cookies.get("clal", domain="lng-tgk-aime-gw.am-all.net")

            if clal is None:
                await interaction.followup.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        title="Error",
                        description="Login was successful, but could not retrieve token.",
                    ),
                    ephemeral=True,
                )
                return

            interaction.client.dispatch(f"chunithm_login_{self.code}", clal)

            await interaction.followup.send(
                embed=discord.Embed(
                    color=discord.Color.green(),
                    title="Success",
                    description="Login successful.",
                ),
                ephemeral=True,
            )

    @override
    async def on_error(self, interaction: Interaction, error: Exception, /) -> None:
        await logger.aexception(
            "error in SEGA ID login modal",
            tag="error_sega_id_login_modal",
            exc_info=error,
        )


class LoginWithSegaIDView(discord.ui.View):
    def __init__(self, code: str, *, timeout: float | None = 180):
        super().__init__(timeout=timeout)

        self.code = code

    @discord.ui.button(label="Login with SEGA ID", style=discord.ButtonStyle.green)
    async def login_with_sega_id(self, interaction: Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(
            SegaIDLoginModal(self.code, timeout=self.timeout)
        )


class LoginFlowPageSource(ListPageSource):
    def __init__(self, code: str, server: str | None) -> None:
        self.code = code

        if server is not None:
            self.script = "javascript:void(function(d){var s=d.createElement('script');s.src='https://gistcdn.githack.com/beer-psi/0eb8d3e50ae753388a6d4a4af5678a2e/raw/ede9859c40741d4dad49a035857b30a3e21c5dce/login.js' ;d.body.append(s)}(document))\n"
            fragment = f"#otp={code}&server={server}"
        else:
            self.script = "javascript:void(function(d){var s=d.createElement('script');s.src='https://gistcdn.githack.com/beer-psi/0eb8d3e50ae753388a6d4a4af5678a2e/raw/c096f619a3a207b99a0cbb63e1d214a7b1af4f28/login2.js' ;d.body.append(s)}(document))\n"
            fragment = ""

        items = [
            (
                "**Step 1:**\n"
                "Log into [CHUNITHM-NET](https://chunithm-net-eng.com) in an incognito/private window.\n"
                "(right click and copy link on desktop, long press and copy link on mobile)"
            ),
            (
                "**Step 2**:\n"
                f"Copy [this link](https://lng-tgk-aime-gw.am-all.net/common_auth/{fragment}) and paste it in the current incognito window.\n"
                'The website should display "Not Found".'
            ),
            (
                "**Step 3**:\n\n"
                "**Desktop users:**\n"
                "Copy the script above and paste it in your browser's developer console (Ctrl + Shift + I or F12).\n\n"
                "**Mobile users:**\n"
                '1. Long press the message above and select "Copy Text".\n'
                "2. Create a bookmark in your browser and paste the copied text in the URL field.\n"
                "3. Run the bookmark.\n\n"
                "This script cannot access your Aime account! It can only access CHUNITHM-NET.\n"
                "\n"
            ),
        ]

        if code is None or server is None:
            items[2] += (
                "The website will display the login command. Copy it and paste it in the bot's DMs."
            )
        else:
            items[2] += (
                f"If the website asks for a passcode, enter **{code}**.\n"
                f"If the website asks for a server, enter **{escape_markdown(server)}**.\n"
            )

        super().__init__(items, per_page=1)

    @override
    async def format_page(
        self, menu: "PaginationView", page: list[str]
    ) -> dict[str, Any]:
        embed = discord.Embed(
            color=discord.Color.yellow(),
            title="How to login",
            description=page[0],
        )
        kwargs: dict[str, Any] = {"embed": embed}

        if menu.current_page == 2:
            kwargs["content"] = self.script

        return kwargs


class LoginFlowView(PaginationView):
    def __init__(self, ctx: Context, code: str, server: str | None = None):
        super().__init__(
            ctx,
            LoginFlowPageSource(code, server),
        )
        self.code = code
        self.add_item(self.login_with_sega_id)

    @override
    async def show_page(self, interaction: Interaction, page_number: int):
        if page_number != 0:
            self.remove_item(self.login_with_sega_id)
        else:
            self.add_item(self.login_with_sega_id)

        return await super().show_page(interaction, page_number)

    @discord.ui.button(
        label="Login with SEGA ID", style=discord.ButtonStyle.danger, row=1
    )
    async def login_with_sega_id(self, interaction: Interaction, _: discord.ui.Button):
        await interaction.response.send_message(
            content=(
                "If you use SEGA ID to log in, you can use this method instead of the normal login process.\n"
                "\n"
                "**Your username and password will not be stored, logged, or shared, and is only kept in temporary memory "
                "for the duration of the login process. If you wish, you may inspect the [source code](https://github.com/beer-psi/chuni-penguin).**\n"
                "\n"
                "If you do not feel safe, please continue with the normal login process."
            ),
            ephemeral=True,
            view=LoginWithSegaIDView(self.code, timeout=self.timeout),
        )
