from asyncio import Task
from types import SimpleNamespace
from typing import TYPE_CHECKING

from discord.channel import CategoryChannel, ForumChannel
from discord.enums import ButtonStyle
from discord.ext.commands.context import DeferTyping
from discord.interactions import Interaction
from discord.message import Message
from discord.ui import Button, View, button

if TYPE_CHECKING:
    from cogs.gaming import GamingCog


class SkipButtonView(View):
    task: Task
    message: Message

    def __init__(self):
        super().__init__(timeout=20)

    async def on_timeout(self):
        self.clear_items()
        await self.message.edit(view=self)

    @button(label="⏩", style=ButtonStyle.danger)
    async def skip(self, interaction: Interaction, _: Button):
        await interaction.response.defer()
        await self.on_timeout()
        self.task.cancel()


class NextGameButtonView(View):
    def __init__(self, cog: "GamingCog", sessions: dict[int, Task]):
        super().__init__(timeout=None)
        self.cog = cog
        self.sessions = sessions

    @button(label="New game", style=ButtonStyle.green, custom_id="new_guess_game")
    async def new_game(self, interaction: Interaction, button: Button):
        if (
            isinstance(interaction.channel, (ForumChannel, CategoryChannel))
            or interaction.channel_id in self.sessions
            or interaction.channel is None
        ):
            return await interaction.response.defer()

        cursed_context = SimpleNamespace()

        # The class only calls .defer, which interaction.response also has.
        cursed_context.typing = lambda: DeferTyping(
            interaction.response, ephemeral=True
        )  # type: ignore[reportGeneralTypeIssues]

        cursed_context.author = interaction.user
        cursed_context.guild = interaction.guild
        cursed_context.channel = interaction.channel
        cursed_context.reply = interaction.channel.send
        cursed_context.send = interaction.channel.send

        # This has all the functions that guess() needs.
        await self.cog.guess(cursed_context)  # type: ignore[reportGeneralTypeIssues]
        return None
