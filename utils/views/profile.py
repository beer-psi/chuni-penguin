import functools
import re
from typing import TYPE_CHECKING, Optional, cast, override

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


async def handle_add_friend_interaction(
    interaction: Interaction,
    user_id: int,
    name: str,
    friend_code: str | None,
):
    embed = discord.Embed(
        title="Error",
        color=discord.Color.red(),
    )

    await interaction.response.defer(ephemeral=True, thinking=True)

    if interaction.user.id == user_id:
        embed.description = "You can't add yourself as a friend, silly!"

        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if friend_code is None:
        embed.description = "There is no friend code data?!"

        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    utils: "UtilsCog" = cast(
        "UtilsCog", cast("ChuniBot", interaction.client).get_cog("Utils")
    )

    ctx = utils.chuninet(interaction, interaction.user.id)

    try:
        client = await ctx.__aenter__()

        await client.send_friend_request(friend_code)

        embed.title = "Success"
        embed.description = f"Sent a friend request to {name}."
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


class PersistentHideFriendCodeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"hide-friend-code:(?P<id>[0-9]+)",
):
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

        super().__init__(
            discord.ui.Button(
                label="Hide friend code",
                style=discord.ButtonStyle.gray,
                custom_id=f"hide-friend-code:{user_id}",
            )
        )

    @classmethod
    @override
    async def from_custom_id(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        interaction: Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        user_id = int(match["id"])

        return cls(user_id)

    @override
    async def interaction_check(self, interaction: Interaction, /) -> bool:
        return interaction.user.id == self.user_id

    @override
    async def callback(self, interaction: Interaction):
        await interaction.response.edit_message(content="_ _", view=None)


class PersistentSendFriendRequestButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"send-friend-request:(?P<user_id>[0-9]+):(?P<friend_code>[0-9]+):(?P<name>.{1,8})",
):
    def __init__(self, user_id: int, friend_code: str, name: str) -> None:
        self.user_id = user_id
        self.friend_code = friend_code
        self.name = name

        super().__init__(
            discord.ui.Button(
                label="Send friend request",
                style=discord.ButtonStyle.green,
                custom_id=f"send-friend-request:{user_id}:{friend_code}:{name}",
            )
        )

    @classmethod
    @override
    async def from_custom_id(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        interaction: Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        user_id = int(match["user_id"])
        friend_code: str = match["friend_code"]
        name: str = match["name"]

        return cls(user_id, friend_code, name)

    @override
    async def callback(self, interaction: Interaction):
        await handle_add_friend_interaction(
            interaction,
            self.user_id,
            self.name,
            self.friend_code,
        )


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

        if not self.profile.friend_code:
            self.clear_items()

    async def on_timeout(self) -> None:
        if self.friend_code_visible and self.profile.friend_code is not None:
            persistent_view = discord.ui.View(timeout=None)
            persistent_view.add_item(PersistentHideFriendCodeButton(self.ctx.author.id))
            persistent_view.add_item(
                PersistentSendFriendRequestButton(
                    self.ctx.author.id, self.profile.friend_code, self.profile.name
                )
            )
            await self.message.edit(view=persistent_view)
        elif self.friend_code_visible:
            await self.message.edit(content="_ _", view=None)
        else:
            await self.message.edit(view=None)

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
        return await handle_add_friend_interaction(
            interaction,
            self.ctx.author.id,
            self.profile.name,
            self.profile.friend_code,
        )
