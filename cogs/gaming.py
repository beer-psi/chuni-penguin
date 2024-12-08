import asyncio
import io
from asyncio import CancelledError, TimeoutError
from random import randrange
from threading import Lock
from typing import TYPE_CHECKING

import discord
from aiohttp import ClientSession
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image
from rapidfuzz import fuzz
from sqlalchemy import delete, select, text

from database.models import Alias, GuessScore, Song
from utils import get_jacket_url
from utils.views import NextGameButtonView, SkipButtonView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.botutils import UtilsCog


class GamingCog(commands.Cog, name="Games"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

        self.game_sessions: dict[int, asyncio.Task] = {}
        self.game_sessions_lock = Lock()

    @commands.group("guess", invoke_without_command=True)
    async def guess(self, ctx: Context, mode: str = "lenient"):
        if ctx.channel.id in self.game_sessions:
            # await ctx.reply("There is already an ongoing session in this channel!")
            return

        with self.game_sessions_lock:
            self.game_sessions[ctx.channel.id] = asyncio.create_task(asyncio.sleep(0))

        async with ctx.typing(), self.bot.begin_db_session() as session:
            prefix = await self.utils.guild_prefix(ctx)

            stmt = (
                select(Song)
                .where(Song.genre != "WORLD'S END")
                .order_by(text("RANDOM()"))
                .limit(1)
            )
            song = (await session.execute(stmt)).scalar_one()

            stmt = select(Alias).where(
                (Alias.song_id == song.id)
                & (
                    (Alias.guild_id == -1)
                    | (
                        Alias.guild_id
                        == (ctx.guild.id if ctx.guild is not None else -1)
                    )
                )
            )
            aliases = [song.title] + [
                alias.alias for alias in (await session.execute(stmt)).scalars()
            ]

            jacket_url = get_jacket_url(song)
            async with ClientSession() as session, session.get(jacket_url) as resp:
                jacket_bytes = await resp.read()
                img = Image.open(io.BytesIO(jacket_bytes))

            x = randrange(0, img.width - 90)
            y = randrange(0, img.height - 90)

            img = img.crop((x, y, x + 90, y + 90))

            bytesio = io.BytesIO()
            img.save(bytesio, format="PNG")
            bytesio.seek(0)

            question_embed = discord.Embed(
                title="Guess the song!",
                description=f"You have 20 seconds to guess the song.\nUse `{prefix}skip` to skip.",
            )
            question_embed.set_image(url="attachment://image.png")

            view = SkipButtonView()
            view.message = await ctx.reply(
                content=f"Game started by {ctx.author.mention}",
                embed=question_embed,
                file=discord.File(bytesio, "image.png"),
                mention_author=False,
                view=view,
            )

        def check(m: discord.Message):
            if mode == "strict":
                return m.channel == ctx.channel and m.content in aliases

            return (
                m.channel == ctx.channel
                and max(
                    [
                        fuzz.QRatio(m.content, alias, processor=str.lower)
                        for alias in aliases
                    ]
                )
                >= 80
            )

        content = ""
        try:
            view.task = self.game_sessions[ctx.channel.id] = asyncio.create_task(
                self.bot.wait_for("message", check=check, timeout=20)
            )
            msg = await self.game_sessions[ctx.channel.id]
            await self._increment_score(msg.author.id)
            await msg.add_reaction("✅")

            content = f"{msg.author.mention} has the correct answer!"
        except CancelledError:
            content = "Skipped!"
        except TimeoutError:
            content = "Time's up!"
        finally:
            answers = "\n".join(aliases)
            answer_embed = discord.Embed(
                description=(
                    f"**Answer**: {answers}\n"
                    "\n"
                    f"**Artist**: {song.artist}\n"
                    f"**Category**: {song.genre}"
                )
            )
            answer_embed.set_image(url=jacket_url)

            await ctx.send(
                content=content,
                embed=answer_embed,
                mention_author=False,
                view=NextGameButtonView(self, self.game_sessions),
            )

            with self.game_sessions_lock:
                del self.game_sessions[ctx.channel.id]

            # The whole point was to ignore exceptions.
            return  # noqa: B012

    @commands.hybrid_command("skip")
    async def skip(self, ctx: Context):
        if ctx.channel.id not in self.game_sessions:
            await ctx.reply("There is no ongoing session in this channel!")
            return

        self.game_sessions[ctx.channel.id].cancel()
        return

    @guess.command("leaderboard")
    async def guess_leaderboard(self, ctx: Context):
        async with ctx.typing(), self.bot.begin_db_session() as session:
            stmt = select(GuessScore).order_by(GuessScore.score.desc()).limit(10)
            scores = (await session.execute(stmt)).scalars()

            embed = discord.Embed(title="Guess Leaderboard")
            description = ""
            for idx, score in enumerate(scores):
                description += (
                    f"\u200b{idx + 1}. <@{score.discord_id}>: {score.score}\n"
                )
            embed.description = description
            await ctx.reply(embed=embed, mention_author=False)

    @guess.command("reset", hidden=True)
    @commands.is_owner()
    async def guess_reset(self, ctx: Context):
        """Resets the c>guess leaderboard"""

        async with self.bot.begin_db_session() as session:
            await session.execute(delete(GuessScore))

        await ctx.message.add_reaction("✅")

    async def _increment_score(self, discord_id: int):
        async with self.bot.begin_db_session() as session, session.begin():
            stmt = select(GuessScore).where(GuessScore.discord_id == discord_id)
            score = (await session.execute(stmt)).scalar_one_or_none()

            if score is None:
                score = GuessScore(discord_id=discord_id, score=1)
                session.add(score)
            else:
                score.score += 1
                await session.merge(score)


async def setup(bot: "ChuniBot") -> None:
    cog = GamingCog(bot)
    await bot.add_cog(cog)
    bot.add_view(NextGameButtonView(cog, cog.game_sessions))
