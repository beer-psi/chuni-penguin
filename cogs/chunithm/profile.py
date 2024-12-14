import asyncio
import contextlib
from argparse import ArgumentError
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image

from chunithm_net.exceptions import ChuniNetError
from chunithm_net.models.enums import SkillClass
from utils import shlex_split
from utils.argparse import DiscordArguments
from utils.views.profile import ProfileView

if TYPE_CHECKING:
    from bot import ChuniBot
    from cogs.botutils import UtilsCog


@dataclass
class DrawCoordinates:
    sx: int = 0
    sy: int = 0
    dx_offset: int = 0
    dy: int = 0
    width: int = 0
    height: int = 0
    rotate: int = 0


AVATAR_COORDS = {
    "skinfoot_r": DrawCoordinates(
        sy=204,
        dx_offset=84,
        dy=260,
        width=42,
        height=52,
    ),
    "skinfoot_l": DrawCoordinates(
        sx=42,
        sy=204,
        dx_offset=147,
        dy=260,
        width=42,
        height=52,
    ),
    "skin": DrawCoordinates(
        dx_offset=72,
        dy=73,
        width=128,
        height=204,
    ),
    "wear": DrawCoordinates(
        dx_offset=7,
        dy=86,
        width=258,
        height=218,
    ),
    "face": DrawCoordinates(
        dx_offset=107,
        dy=80,
        width=58,
        height=64,
    ),
    "face_cover": DrawCoordinates(dx_offset=78, dy=76, width=116, height=104),
    "head": DrawCoordinates(
        width=200,
        height=150,
        dx_offset=37,
        dy=8,
    ),
    "hand_r": DrawCoordinates(
        width=36,
        height=72,
        dx_offset=52,
        dy=158,
    ),
    "hand_l": DrawCoordinates(
        width=36,
        height=72,
        dx_offset=184,
        dy=158,
    ),
    "item_r": DrawCoordinates(width=100, height=272, dx_offset=9, dy=30, rotate=-5),
    "item_l": DrawCoordinates(
        sx=100, width=100, height=272, dx_offset=163, dy=30, rotate=5
    ),
}


def render_avatar(items: dict[str, bytes]) -> BytesIO:
    avatar = Image.open(BytesIO(items["base"]))

    # crop out the USER AVATAR text at the top
    avatar = avatar.crop((0, 20, avatar.width, avatar.height))

    back = Image.open(BytesIO(items["back"]))

    base_x = int((avatar.width - back.width) / 2)
    avatar.paste(back, (base_x, 25), back)

    for name, coords in AVATAR_COORDS.items():
        image = Image.open(BytesIO(items[name]))
        crop = image.crop(
            (
                coords.sx,
                coords.sy,
                coords.sx + coords.width,
                coords.sy + coords.height,
            )
        ).rotate(coords.rotate, expand=True, resample=Image.Resampling.BICUBIC)
        avatar.paste(crop, (base_x + coords.dx_offset, coords.dy), crop)

    buffer = BytesIO()
    avatar.save(buffer, "png", optimize=True)
    buffer.seek(0)
    return buffer


class ProfileCog(commands.Cog, name="Profile"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils: "UtilsCog" = self.bot.get_cog("Utils")  # type: ignore[reportGeneralTypeIssues]

    @commands.hybrid_command(name="avatar")
    async def avatar(
        self, ctx: Context, *, user: Optional[discord.User | discord.Member] = None
    ):
        """View your CHUNITHM avatar."""
        async with ctx.typing(), self.utils.chuninet(
            ctx if user is None else user.id
        ) as client:
            basic_data = await client.authenticate()
            avatar_urls = basic_data.avatar

            async def task(url):
                resp = await client.session.get(url)
                async with contextlib.aclosing(resp) as resp:
                    return await resp.aread()

            tasks = [
                task(avatar_urls.base),
                task(avatar_urls.back),
            ]
            tasks.extend(task(getattr(avatar_urls, name)) for name in AVATAR_COORDS)
            results = await asyncio.gather(*tasks)
            items: dict[str, bytes] = dict(
                zip(
                    ["base", "back", *AVATAR_COORDS],
                    results,
                )
            )

        buffer = await asyncio.to_thread(render_avatar, items)
        await ctx.reply(
            content=f"Avatar of {basic_data.name}",
            file=discord.File(buffer, filename="avatar.png"),
            mention_author=False,
        )

    async def _kamaitachi_profile_card(self, user_id: int):
        async with self.utils.kamaitachi_client(user_id) as client:
            resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
            data = resp.json()

            if not data["success"]:
                msg = f"Could not get Kamaitachi profile: {data['description']}"
                raise commands.CommandError(msg)

            user_id = data["body"]["id"]
            username = data["body"]["username"]

            resp = await client.get(
                "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single"
            )
            data = resp.json()

            if not data["success"]:
                msg = f"Could not get Kamaitachi game stats: {data['description']}"
                raise commands.CommandError(msg)

            stats = data["body"]

        embed = discord.Embed(
            title=username,
            color=0xCA1961,
            url=f"https://kamai.tachi.ac/u/{username}/games/chunithm/Single",
        )
        description = ""

        if "dan" in stats["gameStats"]["classes"]:
            medal = getattr(
                SkillClass, stats["gameStats"]["classes"]["dan"].replace("DAN_", "")
            )
            description = f"Class {medal}"

            if "emblem" in stats["gameStats"]["classes"]:
                emblem = getattr(
                    SkillClass,
                    stats["gameStats"]["classes"]["emblem"].replace("DAN_", ""),
                )
                description += f", cleared all of class {emblem}"

            description += "."

        description = (
            f"{description}\n"
            f"▸ **NaiveRating**: {stats['gameStats']['ratings']['naiveRating']:.2f}\n"
            f"▸ **Scores**: {stats['totalScores']}\n"
            f"▸ **Session Playtime**: {stats['playtime'] // (60 * 60 * 1000)} hours\n"
        )

        if (
            stats["mostRecentScore"] is not None
            and stats["mostRecentScore"]["timeAchieved"] is not None
        ):
            ts = datetime.fromtimestamp(
                stats["mostRecentScore"]["timeAchieved"] / 1000, tz=UTC
            )
            last_played = f"<t:{int(ts.timestamp())}:f>"
            description += f"▸ **Last played**: {last_played}\n"

        embed.description = description

        return embed

    async def _chunithm_net_profile_card(self, user_id: int):
        async with self.utils.chuninet(user_id) as client:
            player_data = await client.player_data()

            optional_data: list[str] = []
            if player_data.team is not None:
                optional_data.append(f"Team {player_data.team.name}")
            if player_data.medal is not None:
                content = f"Class {player_data.medal}"
                if player_data.emblem is not None:
                    content += f", cleared all of class {player_data.emblem}"
                content += "."
                optional_data.append(content)
            optional_data_joined = "\n".join(optional_data)

            level = str(player_data.lv)
            if player_data.reborn > 0:
                level = f"{player_data.reborn}⭐ + {level}"

            description = (
                f"{optional_data_joined}\n"
                f"▸ **Level**: {level}\n"
                f"▸ **Rating**: {player_data.rating.current:.2f} (MAX {player_data.rating.max:.2f})\n"
                f"▸ **OVER POWER**: {player_data.overpower.value:.2f} ({player_data.overpower.progress * 100:.2f}%)\n"
                f"▸ **Plays**: {player_data.playcount}\n"
            )

            if player_data.last_play_date:
                description += f"▸ **Last played**: <t:{int(player_data.last_play_date.timestamp())}:f>\n"

            embed = discord.Embed(
                title=player_data.name,
                description=description,
                color=player_data.possession.color(),
            ).set_author(name=player_data.nameplate.content)

            if player_data.character_frame is None:
                files = []
                embed = embed.set_thumbnail(url=player_data.character)
            elif player_data.character is not None:
                character_resp, charaframe_resp = await asyncio.gather(
                    client.session.get(player_data.character),
                    client.session.get(player_data.character_frame),
                )

                character = Image.open(BytesIO(character_resp.content))
                charaframe = Image.open(BytesIO(charaframe_resp.content))

                character = character.resize((87, 87), Image.Resampling.LANCZOS)
                charaframe = charaframe.resize((98, 98), Image.Resampling.LANCZOS)

                charaframe.paste(character, (6, 6), character)

                avatar = BytesIO()
                charaframe.save(avatar, "PNG", optimize=True)
                avatar.seek(0)

                files = [discord.File(avatar, filename="avatar.png")]
                embed = embed.set_thumbnail(url="attachment://avatar.png")
            else:
                files = []

            return player_data, embed, files

    async def _chunithm_inner(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        async with ctx.typing():
            if kamaitachi:
                embed = await self._kamaitachi_profile_card(target_id)

                await ctx.reply(embed=embed, mention_author=False)
            else:
                profile_data, embed, files = await self._chunithm_net_profile_card(
                    target_id
                )
                view = ProfileView(ctx, profile_data)
                view.message = await ctx.reply(
                    embed=embed,
                    files=files,
                    view=view if user is None else None,  # pyright: ignore[reportArgumentType]
                    mention_author=False,
                )

    @commands.command(name="chunithm", aliases=["chuni", "profile"])
    async def chunithm(
        self,
        ctx: Context,
        *,
        query: str = "",
    ):
        """View your CHUNITHM profile.

        **Parameters**:
        `user`: The user to view the profile of.
        `-k, --kamaitachi`: Whether to view their Kamaitachi CHUNITHM profile instead.
        """

        parser = DiscordArguments()
        parser.add_argument("-k", "--kamaitachi", action="store_true")

        try:
            args, rest = await parser.parse_known_intermixed_args(shlex_split(query))
        except ArgumentError as e:
            raise commands.BadArgument(str(e)) from e

        user = None

        if len(rest) > 0:
            for converter in [commands.MemberConverter, commands.UserConverter]:
                with contextlib.suppress(commands.BadArgument):
                    user = await converter().convert(ctx, rest[0])
                    break

        await self._chunithm_inner(ctx, user, kamaitachi=args.kamaitachi)

    @app_commands.command(name="chunithm", description="View your CHUNITHM profile.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to view the profile of",
        kamaitachi="Whether to view their Kamaitachi CHUNITHM profile instead",
    )
    async def chunithm_slash(
        self,
        interaction: discord.Interaction,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await Context.from_interaction(interaction)

        await self._chunithm_inner(ctx, user, kamaitachi=kamaitachi)

    @commands.hybrid_command(name="rename")
    async def rename(self, ctx: Context, *, new_name: str):
        """Use magical powers to change your IGN.

        Please note that this will change the actual display name of your CHUNITHM account.

        Parameters
        ----------
        new_name: str
            The username you want to change to.
            Your username can include up to 8 characters, excluding specific characters. You can also use the following symbols.
            ． ・ ： ； ？ ！ ～ ／ ＋ － × ÷ ＝ ♂ ♀ ∀ ＃ ＆ ＊ ＠ ☆ ○ ◎ ◇ □ △ ▽ ♪ † ‡ Σ α β γ θ φ ψ ω Д ё
        """  # noqa: RUF002

        async with ctx.typing(), self.utils.chuninet(ctx) as client:
            try:
                await client.change_player_name(new_name)
                await ctx.reply("Your username has been changed.", mention_author=False)
            except ValueError as e:
                msg = str(e)

                if msg == "文字数が多すぎます。":  # Too many characters
                    msg = "The new username is too long (only 8 characters allowed)."

                raise commands.BadArgument(msg) from None
            except ChuniNetError as e:
                if e.code == 110106:
                    msg = "The new username contains a banned word."
                    raise commands.BadArgument(msg) from None

                raise


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ProfileCog(bot))
