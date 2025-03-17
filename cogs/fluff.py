import random
from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

if TYPE_CHECKING:
    from bot import ChuniBot

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
    def __init__(self) -> None:
        self.random = random.Random()
        self.random.seed()

    @commands.hybrid_command("8ball")
    @app_commands.describe(question="A question to ask the mysterious 8ball")
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


async def setup(bot: "ChuniBot"):
    await bot.add_cog(FluffCog())
