import random
from typing import TYPE_CHECKING

import discord
from discord import (
    DeletedReferencedMessage,
    app_commands,
)
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown

from chuni_penguin.context import PenguinContext
from chuni_penguin.logging import logged_prefix_command

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot

EIGHT_BALL_RESPONSES = [
    "Most definitely yes.",
    "For sure.",
    "Totally!",
    "Of course!",
    "As I see it, yes.",
    "My sources say yes.",
    "Yes.",
    "Most likely.",
    "Perhaps...",
    "Maybe...",
    "Hm, not sure.",
    "It is uncertain.",
    "Ask me again later.",
    "Don't count on it.",
    "Probably not.",
    "Very doubtful.",
    "Most likely no.",
    "Nope.",
    "No.",
    "My sources say no.",
    "Don't even think about it.",
    "Definitely no.",
    "NO - It may cause disease contraction!",
]


class FluffCog(commands.Cog, name="Fluff"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot: "ChuniBot" = bot

        self.random = random.Random()
        self.random.seed()

    @commands.hybrid_command("8ball", extras={"invoke_on_edit": False})
    @app_commands.describe(question="A question to ask the mysterious 8ball")
    @logged_prefix_command
    async def eight_ball(self, ctx: Context, *, question: str):
        """Ask the 8ball a question. It can only respond with yes or no.

        Parameters
        ----------
        question: str
            A question to ask the 8ball. It must end with a question mark.
        """
        if not question.endswith("?"):
            msg = "That doesn't look like a question."
            raise commands.BadArgument(msg)

        await ctx.reply(
            content=self.random.choice(EIGHT_BALL_RESPONSES), mention_author=False
        )

    @commands.hybrid_command("quitting")
    @logged_prefix_command
    async def quitting(self, ctx: Context):
        """I'LL NEVER PLAY THIS CRAPPY GAME AGAIN!"""

        if (
            (reference := ctx.message.reference) is not None
            and reference.message_id is not None
            and not isinstance(reference.resolved, DeletedReferencedMessage)
        ):
            channel = self.bot.get_partial_messageable(
                reference.channel_id,
                guild_id=reference.guild_id,
            )
            target = channel.get_partial_message(reference.message_id)
        else:
            target = ctx

        await target.reply(
            content="https://cdn.discordapp.com/attachments/1091952903016697947/1358802119179636786/mfw-quitting.jpg",
            mention_author=False,
        )

    @commands.hybrid_command("ock")
    @logged_prefix_command
    async def ock(self, ctx: Context):
        await ctx.reply(
            content="https://tenor.com/view/dripping-cock-chicken-among-us-drip-gif-21478744",
            mention_author=False,
        )

    @commands.hybrid_command("ar")
    @logged_prefix_command
    async def ar(self, ctx: Context):
        await ctx.reply(
            content="https://cdn.discordapp.com/attachments/785983013430231081/1385525318642827316/twitter_1935670382146855418.gif",
            mention_author=False,
        )

    @commands.hybrid_command("eastereggs", aliases=["easter"])
    @logged_prefix_command
    async def easter_eggs(self, ctx: PenguinContext):
        count = await ctx.bot.database.count_easter_eggs_found(ctx.author.id)

        await ctx.reply(
            content=f"You've found {count}/8 easter eggs!",
            mention_author=False,
        )

    @commands.hybrid_command("heck", aliases=["check"])
    @logged_prefix_command
    async def check(
        self, ctx: PenguinContext, *, target: discord.Member | discord.User
    ):
        """They need to check them cab and game....."""

        name = escape_markdown(target.display_name)

        if ctx.guild is not None:
            server_name = escape_markdown(ctx.guild.name)
        else:
            server_name = "PRO"

        await ctx.reply(
            content=f"{name} skilled player but that is not normally, This very very insane....They need to check them cab and game.....Maybe they not cheating but maybe they using the game deficit ...and this cant seem on game screen..They need to check-up...{name} using game deficit on {server_name} scene ,ON BIG scoreposting. Maybe everyone dont knows them trick.They incredible....I want to ask their where is the comming of your skill's ?",
            mention_author=False,
        )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(FluffCog(bot))
