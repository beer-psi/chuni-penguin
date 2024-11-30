import functools
from typing import TYPE_CHECKING, Optional, cast

import discord.ui
from discord import ButtonStyle, Interaction
from discord.ext import commands
from discord.ext.commands import Context

from chunithm_net.exceptions import (
    AlreadyAddedAsFriend,
    ChuniNetError,
    InvalidFriendCode,
)

if TYPE_CHECKING:
    from bot import ChuniBot
    from chunithm_net.models.player_data import PlayerData
    from cogs.botutils import UtilsCog


class ProfileView(discord.ui.View):
    message: discord.Message

    def __init__(
        self, ctx: Context, profile: "PlayerData", *, timeout: Optional[float] = 120
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.profile = profile
        self.friend_code_visible = False
        self.send_friend_request_button = None

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[reportGeneralTypeIssues]
        self.clear_items()

        if self.friend_code_visible:
            await self.message.edit(content="_ _", view=self)
        else:
            await self.message.edit(view=self)

    @discord.ui.button(label="Show friend code")
    async def show_hide_friend_code(
        self, interaction: Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.ctx.author:
            await interaction.response.defer()
            return

        if not self.friend_code_visible:
            self.friend_code_visible = True
            button.label = "Hide friend code"

            self.send_friend_request_button = discord.ui.Button(
                style=ButtonStyle.green, label="Send friend request"
            )
            self.send_friend_request_button.callback = functools.partial(
                self.send_friend_request, button=self.send_friend_request_button
            )
            self.add_item(self.send_friend_request_button)

            await interaction.response.edit_message(
                content=f"Friend code: {self.profile.friend_code}", view=self
            )
        else:
            self.friend_code_visible = False
            button.label = "Show friend code"

            if self.send_friend_request_button is not None:
                self.remove_item(self.send_friend_request_button)

            await interaction.response.edit_message(content="_ _", view=self)

    async def send_friend_request(
        self, interaction: Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="Error",
            color=discord.Color.red(),
        )

        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.user == self.ctx.author:
            embed.description = "You can't add yourself as a friend, silly!"

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if (friend_code := self.profile.friend_code) is None:
            embed.description = "There is no friend code data?!"

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        utils: "UtilsCog" = cast(
            "UtilsCog", cast("ChuniBot", interaction.client).get_cog("Utils")
        )
        ctx = utils.chuninet(interaction.user.id)

        try:
            client = await ctx.__aenter__()

            await client.send_friend_request(friend_code)

            embed.title = "Success"
            embed.description = f"Sent a friend request to {self.profile.name}."
            embed.color = discord.Color.green()
        except AlreadyAddedAsFriend:
            embed.description = "You've already added this player as a friend!"
        except InvalidFriendCode:
            embed.description = "Could not send a friend request because the friend code was invalid, or you're trying to send a friend request to yourself."
        except ChuniNetError as e:
            embed.description = f"CHUNITHM-NET error {e.code}: {e.description}"
        except commands.BadArgument as e:
            embed.description = str(e)
        finally:
            await ctx.__aexit__(None, None, None)

        await interaction.followup.send(embed=embed, ephemeral=True)
