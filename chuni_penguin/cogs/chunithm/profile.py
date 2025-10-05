import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Literal, override

import discord
import httpx
import magic
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image
from sqlalchemy import select

from chuni_penguin import flags
from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.converters import MemberOrUserConverter
from chuni_penguin.database import UserConfig
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.networks.chunithm_net import ChuniNetError, SkillClass
from chuni_penguin.ui import (
    LoginBonusView,
    PersistentHideFriendCodeButton,
    PersistentSendFriendRequestButton,
    ProfileView,
)
from chuni_penguin.utils import json_loads

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


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
    "item_r": DrawCoordinates(width=100, height=272, dx_offset=-3, dy=26, rotate=5),
    "item_l": DrawCoordinates(
        sx=100, width=100, height=272, dx_offset=151, dy=26, rotate=-5
    ),
    "front": DrawCoordinates(dy=10, width=272, height=294),
}


def render_avatar(items: dict[str, bytes]) -> BytesIO:
    avatar = Image.open(BytesIO(items["base"]))

    # crop out the USER AVATAR text at the top
    avatar = avatar.crop((0, 20, avatar.width, avatar.height))

    back = Image.open(BytesIO(items["back"]))

    base_x = int((avatar.width - back.width) / 2)
    avatar.paste(back, (base_x, 5), back)

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


async def guess_mime_type(response: httpx.Response) -> str:
    data = BytesIO()

    async for chunk in response.aiter_bytes():
        if data.tell() == 0:
            # some simple and common formats can be checked first without
            # calling into libmagic
            fourcc = chunk[:4]

            if fourcc == b"GIF8":
                return "image/gif"

            if fourcc == b"\x89PNG":
                return "image/png"

            if fourcc[:3] == b"\xff\xd8\xff" and fourcc[3] in (0xDB, 0xE0, 0xE1, 0xEE):
                return "image/jpeg"

            if fourcc == b"RIFF" and fourcc[8:12] == b"WEBP":
                return "image/webp"

        data.write(chunk)

        if data.tell() >= 2048:
            break

    return magic.from_buffer(data.getvalue(), mime=True)


class ProfileCog(commands.Cog, name="Profile"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils

    @override
    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(PersistentHideFriendCodeButton)
        self.bot.add_dynamic_items(PersistentSendFriendRequestButton)

    @commands.hybrid_command(name="avatar")
    @commands.bot_has_permissions(attach_files=True)
    @logged_prefix_command
    async def avatar(
        self,
        ctx: Context,
        *,
        user: discord.User | discord.Member = commands.Author,
    ):
        """View your CHUNITHM avatar."""
        async with (
            ctx.typing(),
            self.utils.chuninet(ctx, user.id) as client,
        ):
            basic_data = await client.authenticate()
            avatar_urls = basic_data.avatar

            async def task(url):
                resp = await self.bot.caching_http_client.get(url)

                async with contextlib.aclosing(resp) as resp:
                    return await resp.aread()

            tasks = [
                task(avatar_urls.base),
                task(avatar_urls.back),
            ]
            tasks.extend(task(getattr(avatar_urls, name)) for name in AVATAR_COORDS)
            results = await asyncio.gather(*tasks)
            items: dict[str, bytes] = dict(
                zip(  # noqa: B905
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

    async def _kamaitachi_profile_card(self, ctx: Context, user_id: int):
        async with self.utils.kamaitachi_client(ctx, user_id) as client:
            resp = await client.get("https://kamai.tachi.ac/api/v1/users/me")
            data = json_loads(resp.content)

            if not data["success"]:
                msg = f"Could not get Kamaitachi profile: {data['description']}"
                raise commands.CommandError(msg)

            user_id = data["body"]["id"]
            username = data["body"]["username"]
            custom_banner_location = data["body"]["customBannerLocation"]
            custom_pfp_location = data["body"]["customPfpLocation"]

            # Discord really doesn't like image files without extensions, hence
            # this stupid hack.
            if custom_banner_location is not None:
                async with client.stream_banner(
                    user_id, custom_banner_location
                ) as response:
                    mime = await guess_mime_type(response)

                    if mime.startswith("image/"):
                        custom_banner_location += f".{mime[6:]}"

            if custom_pfp_location is not None:
                async with client.stream_pfp(user_id, custom_pfp_location) as response:
                    mime = await guess_mime_type(response)

                    if mime.startswith("image/"):
                        custom_pfp_location += f".{mime[6:]}"

            resp = await client.get(
                "https://kamai.tachi.ac/api/v1/users/me/games/chunithm/Single"
            )
            data = json_loads(resp.content)

            if not data["success"]:
                msg = f"Could not get Kamaitachi game stats: {data['description']}"
                raise commands.CommandError(msg)

            stats = data["body"]

        embed = discord.Embed(
            title=username,
            color=0xCA1961,
            url=f"https://kamai.tachi.ac/u/{username}/games/chunithm/Single",
        )

        if (
            config.web.enable
            and config.web.base_url is not None
            and "localhost" not in config.web.base_url
            and "127.0.0.1" not in config.web.base_url
        ):
            if custom_banner_location is not None:
                embed.set_image(
                    url=f"{config.web.base_url}/kamaitachi/users/{user_id}/banner/{custom_banner_location}"
                )
            if custom_pfp_location is not None:
                embed.set_thumbnail(
                    url=f"{config.web.base_url}/kamaitachi/users/{user_id}/pfp/{custom_pfp_location}"
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
            f"▸ **NaiveRating**: {round(stats['gameStats']['ratings']['naiveRating'] * 100) / 100:.2f}\n"
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

    async def _chunithm_net_profile_card(self, ctx: Context, user_id: int):
        async with self.utils.chuninet(ctx, user_id) as client:
            player_data = await client.player_data()
            collections = await client.current_collections()

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

            titles = "\n".join([f"**{t.content}**" for t in player_data.titles])

            description = (
                f"{titles}\n"
                f"### {player_data.name}\n"
                f"{optional_data_joined}\n"
                f"▸ **Level**: {level}\n"
                f"▸ **Rating**: {player_data.rating:.2f}\n"
                f"▸ **OVER POWER**: {player_data.overpower.value:.2f} ({player_data.overpower.progress * 100:.2f}%)\n"
                f"▸ **Plays**: {player_data.playcount}\n"
            )

            if player_data.last_play_date:
                description += f"▸ **Last played**: <t:{int(player_data.last_play_date.timestamp())}:f>\n"

            embed = discord.Embed(
                description=description,
                color=player_data.possession.color(),
            )
            embed.set_image(url=collections.nameplate)

            if player_data.character_frame is None:
                files = []
                embed = embed.set_thumbnail(url=player_data.character)
            elif player_data.character is not None:
                character_resp, charaframe_resp = await asyncio.gather(
                    self.bot.caching_http_client.get(player_data.character),
                    self.bot.caching_http_client.get(player_data.character_frame),
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

        kamaitachi = (
            await self.utils.choose_preferred_network(
                ctx, target_id, kamaitachi=kamaitachi
            )
            == "kamaitachi"
        )

        async with ctx.typing():
            if kamaitachi:
                embed = await self._kamaitachi_profile_card(ctx, target_id)

                await ctx.reply(embed=embed, mention_author=False)
            else:
                profile_data, embed, files = await self._chunithm_net_profile_card(
                    ctx, target_id
                )
                view = ProfileView(ctx, profile_data)
                view.message = await ctx.reply(
                    embed=embed,
                    files=files,
                    view=view if user is None else None,  # pyright: ignore[reportArgumentType]
                    mention_author=False,
                )

    @flags.command(name="chunithm", aliases=["chuni", "profile"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("user", nargs="?", default=None, type=MemberOrUserConverter)
    @logged_prefix_command
    async def chunithm(
        self,
        ctx: Context,
        *,
        kamaitachi: bool = False,
        user: discord.Member | discord.User | None = None,
    ):
        """View your CHUNITHM profile.

        **Parameters**:
        `user`: The user to view the profile of.
        `-k, --kamaitachi`: Whether to view their Kamaitachi CHUNITHM profile instead.
        """

        await self._chunithm_inner(ctx, user=user, kamaitachi=kamaitachi)

    @app_commands.command(name="chunithm", description="View your CHUNITHM profile.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to view the profile of",
        kamaitachi="Whether to view their Kamaitachi CHUNITHM profile instead",
    )
    @logged_app_command
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
    @logged_prefix_command
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

    @commands.hybrid_command("config")
    @app_commands.describe(
        key="The option you want to change or view.",
        value="The value to change the option to. Leave blank to see the current value.",
    )
    @app_commands.choices(
        key=[
            app_commands.Choice(
                name="synthesis-alt-jacket", value="synthesis-alt-jacket"
            ),
            app_commands.Choice(name="privacy", value="privacy"),
        ]
    )
    @logged_prefix_command
    async def config(
        self,
        ctx: Context,
        key: Literal["synthesis-alt-jacket", "privacy"],
        value: str | None = None,
    ):
        """Adjust your experience with the bot.

        Currently, these options are supported:
        - `synthesis-alt-jacket`: Changes the jacket art for the song "Synthesis." whereever applicable. The possible options are `none` (black background), `default` (use CHUNITHM's jacket art), `cytus2`, `vividstasis`, `musedash`, `musicdiver`.
        - `privacy`: Do not allow other users to view your profile and scores using the bot. You can still use commands, but to others it will seem like you're not logged in. The possible options are `true` (enabled) and `false` (disabled).

        **Parameters:**
        `key`: The option you want to change or view.
        `value`: The value to change the option to. Leave blank to see the current value for the given option.

        **Examples:**
        `/config synthesis-alt-jacket cytus2`
        `/config privacy true`
        """

        if key != "synthesis-alt-jacket" and key != "privacy":
            msg = "Expected option to be `synthesis-alt-jacket` or `privacy`."
            raise ValueError(msg)

        new_config = False

        async with self.bot.begin_db_session() as session:
            query = select(UserConfig).where(UserConfig.discord_id == ctx.author.id)
            result = await session.execute(query)
            user_config = result.scalar_one_or_none()

        if value is None:
            if key == "synthesis-alt-jacket":
                current_value = (
                    user_config.synthesis_alt_jacket if user_config else "default"
                )
            else:
                current_value = (
                    str(user_config.privacy_mode) if user_config else "False"
                )

            await ctx.reply(
                content=f"Your current config for `{key}` is `{current_value}`.",
                mention_author=False,
            )
            return

        value = value.lower()

        if user_config is None:
            new_config = True
            user_config = UserConfig(
                discord_id=ctx.author.id,
                synthesis_alt_jacket="default",
                privacy_mode=False,
            )

        if key == "synthesis-alt-jacket":
            if value not in (
                "none",
                "default",
                "cytus2",
                "vividstasis",
                "musedash",
                "musicdiver",
            ):
                msg = "Invalid option for `synthesis-alt-jacket`. Expected one of `none`, `default`, `cytus2`, `vividstasis`, `musedash`, `musicdiver`."
                raise commands.BadArgument(msg)

            user_config.synthesis_alt_jacket = value
        else:
            if value not in (
                "1",
                "true",
                "t",
                "yes",
                "y",
                "on",
                "0",
                "false",
                "f",
                "no",
                "n",
                "off",
            ):
                msg = "Invalid option for `privacy`. Expected one of `true` or `false`."
                raise commands.BadArgument(msg)

            user_config.privacy_mode = value in ("1", "true", "t", "yes", "y", "on")

        async with self.bot.begin_db_session() as session:
            if new_config:
                session.add(user_config)
            else:
                await session.merge(user_config)

            await session.commit()

        await ctx.reply(
            content=f"Set your config for `{key}` to `{value}`.",
            mention_author=False,
        )

    @commands.hybrid_command("loginbonus")
    @logged_prefix_command
    async def loginbonus(self, ctx: PenguinContext):
        """View your current login bonus progress."""

        async with ctx.typing(), self.utils.chuninet(ctx) as client:
            login_bonus = await client.login_bonus()

        view = LoginBonusView(ctx, login_bonus)
        await view.start()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ProfileCog(bot))
