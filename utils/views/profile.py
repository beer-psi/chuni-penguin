import functools
from typing import TYPE_CHECKING, Optional, cast

from discord.ext import commands
import discord.ui
from discord import ButtonStyle, Interaction
from discord.ext.commands import Context

from chunithm_net.exceptions import InvalidFriendCode

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
        self.send_friend_request_button = None

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[reportGeneralTypeIssues]
        self.clear_items()

        if len(self.message.content) > 0:
            await self.message.edit(content="_ _", view=self)
        else:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        return interaction.user == self.ctx.author

    @discord.ui.button(label="Show friend code")
    async def show_hide_friend_code(
        self, interaction: Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.ctx.author:
            await interaction.response.defer()
            return

        if button.label == "Show friend code":
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
            button.label = "Show friend code"

            if self.send_friend_request_button is not None:
                self.remove_item(self.send_friend_request_button)

            await interaction.response.edit_message(content="_ _", view=self)

    async def send_friend_request(
        self, interaction: Interaction, button: discord.ui.Button
    ):
        if interaction.user == self.ctx.author:
            embed = discord.Embed(
                title="Error",
                description="You can't add yourself as a friend, silly!",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        utils: "UtilsCog" = cast("ChuniBot", interaction.client).get_cog("Utils")

        try:
            ctx = utils.chuninet(interaction.user.id)
            client = await ctx.__aenter__()

            await client.send_friend_request(self.profile.friend_code)

            embed = discord.Embed(
                title="Success",
                description=f"Sent a friend request to {self.profile.name}.",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)
        except InvalidFriendCode:
            embed = discord.Embed(
                title="Error",
                description="Could not send a friend request because the friend code was invalid, or you're trying to send a friend request to yourself.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        except commands.BadArgument as e:
            embed = discord.Embed(
                title="Error",
                description=str(e),
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
