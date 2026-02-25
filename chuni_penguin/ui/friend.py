from typing import TYPE_CHECKING

import discord
from discord.utils import escape_markdown

from chuni_penguin.context import PenguinContext
from chuni_penguin.networks.types import Profile

from ._base import MessageKwargs, PenguinView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class FriendRequestWaitView(PenguinView[PenguinContext]):
    def __init__(
        self, ctx: PenguinContext, bot_profile: Profile, *, timeout: float | None = 180
    ) -> None:
        super().__init__(ctx, timeout=timeout)
        self.bot_profile = bot_profile

    async def _before_start(self, *, content: str | None = None) -> MessageKwargs:
        return {
            "content": content,
            "embed": discord.Embed(
                color=discord.Color.yellow(),
                title="Friend request sent",
                description=f"Please accept the friend request from {escape_markdown(self.bot_profile.username)} to continue.",
            ),
        }

    @discord.ui.button(
        style=discord.ButtonStyle.green, label="I've accepted the friend request"
    )
    async def accepted_friend_request(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Please wait...", embed=None, view=None
        )
        self.stop()
