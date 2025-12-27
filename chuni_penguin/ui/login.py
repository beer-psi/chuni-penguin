from collections.abc import Sequence
from http.cookiejar import CookieJar
from typing import TYPE_CHECKING, override

import discord.ui
import httpx
import httpx_aiohttp
from discord import Interaction
from discord.abc import MISSING
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chuni_penguin.logging import logger
from chuni_penguin.networks.chunithm_net._hooks import _AUTHENTICATION_URL

from ._pagination import FormatPageReturn, ListPageSource, PaginationView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class SegaIDLoginModal(discord.ui.Modal, title="Login with SEGA ID"):
    username = discord.ui.TextInput(label="SEGA ID username", min_length=1)
    password = discord.ui.TextInput(label="SEGA ID password", min_length=1)
    otp = discord.ui.TextInput(
        label="Two-factor authentication code (if enabled)",
        min_length=6,
        max_length=6,
        required=False,
    )

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

    # The client attached to the interaction is definitely ChuniBot.
    @override
    async def on_submit(self, interaction: Interaction["ChuniBot"]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        await interaction.response.defer(ephemeral=True)

        jar = CookieJar()

        async with httpx.AsyncClient(
            cookies=jar,
            timeout=httpx.Timeout(timeout=60.0),
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5),
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

            location = resp.headers.get("location")
            correct_username_password = False

            if location == "https://lng-tgk-aime-gw.am-all.net/common_auth/login/otp":
                correct_username_password = True

                if not self.otp.value:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            color=discord.Color.red(),
                            title="Error",
                            description="Two-factor authentication was enabled, but a code was not provided.",
                        ),
                        ephemeral=True,
                    )
                    return

                resp = await client.post(
                    "https://lng-tgk-aime-gw.am-all.net/common_auth/login/otpauth",
                    data={"password": self.otp.value},
                    follow_redirects=False,
                )
                location = resp.headers.get("location")

            if location is None or "https://chunithm-net-eng.com" not in location:
                if correct_username_password:
                    description = "Invalid two-factor authentication code."
                else:
                    description = "Invalid username or password."

                await interaction.followup.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        title="Error",
                        description=description,
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
        if isinstance(error, discord.NotFound):
            return

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


class LoginFlowPageSource(ListPageSource[FormatPageReturn]):
    def __init__(self, code: str, server: str | None) -> None:
        step_3_description = (
            "**Step 3**:\n"
            "(Save the [login bookmarklet](https://chuni-penguin.beerpsi.cc/bookmarklet/) if you haven't already.)\n\n"
            'Run the login bookmarklet on the "Not found" page opened previously.\n\n'
            "This script cannot access your Aime account! It can only access CHUNITHM-NET.\n"
            "\n"
        )

        if code is None or server is None:
            step_3_description += "The website will display the login command. Copy it and paste it in the bot's DMs."
        else:
            step_3_description += (
                f"If the website asks for a passcode, enter **{code}**.\n"
                f"If the website asks for a server, enter **{escape_markdown(server)}**.\n"
            )

        fragment = f"#otp={code}&server={server}" if server is not None else ""
        items: list[FormatPageReturn] = [
            {
                "content": "",
                "embed": discord.Embed(
                    color=discord.Color.yellow(),
                    title="How to login",
                    description=(
                        "**Step 1:**\n"
                        "Log into [CHUNITHM-NET](https://chunithm-net-eng.com) in an incognito/private window.\n"
                        "(right click and copy link on desktop, long press and copy link on mobile)\n"
                        "\n"
                        "**Remember to enable auto login!**"
                    ),
                ).set_image(
                    url="https://chuni-penguin.beerpsi.cc/assets/images/enable-auto-login.png"
                ),
            },
            {
                "content": "",
                "embed": discord.Embed(
                    color=discord.Color.yellow(),
                    title="How to login",
                    description=(
                        "**Step 2**:\n"
                        f"Copy [this link](https://lng-tgk-aime-gw.am-all.net/common_auth/{fragment}) and paste it in the incognito window.\n"
                        'The website should display "Not found".'
                    ),
                ),
            },
            {
                "content": "",
                "embed": discord.Embed(
                    color=discord.Color.yellow(),
                    title="How to login",
                    description=step_3_description,
                ),
            },
        ]

        super().__init__(items, per_page=1)

    async def format_page(
        self, menu: "PaginationView", page: Sequence[FormatPageReturn]
    ) -> FormatPageReturn:
        return page[0]


class LoginFlowView(PaginationView):
    def __init__(self, ctx: Context, code: str, server: str | None = None):
        super().__init__(
            ctx,
            LoginFlowPageSource(code, server),
        )
        self.code = code
        self.add_item(self.login_with_sega_id)

    @override
    async def show_page(self, interaction: Interaction, page_index: int):
        if page_index != 0:
            self.remove_item(self.login_with_sega_id)
        else:
            self.add_item(self.login_with_sega_id)

        return await super().show_page(interaction, page_index)

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
