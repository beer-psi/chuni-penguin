import asyncio
import contextlib
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Literal, override

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from PIL import Image
from sqlalchemy import select

from chuni_penguin import flags
from chuni_penguin.context import PenguinContext
from chuni_penguin.converters import MemberOrUserConverter
from chuni_penguin.database import Cookie, UserConfig
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.networks.chunithm_net import ChuniNetError
from chuni_penguin.ui import (
    LoginBonusView,
    PersistentHideFriendCodeButton,
    PersistentSendFriendRequestButton,
    ProfileView,
)

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
        ctx: PenguinContext,
        *,
        user: discord.User | discord.Member = commands.Author,
    ):
        """View your CHUNITHM avatar."""
        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, user.id, chunithm_net=True
            ) as client,
        ):
            if not client.SUPPORTS_USER_AVATAR_IN_PROFILE:
                msg = f"Network {client.NAME} does not support penguin avatars."
                raise commands.CommandError(msg)

            basic_data = await client.get_minimal_profile()
            avatar_urls = basic_data.user_avatar

            assert avatar_urls is not None

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
            content=f"Avatar of {basic_data.username}",
            file=discord.File(buffer, filename="avatar.png"),
            mention_author=False,
        )

    async def _chunithm_inner(
        self,
        ctx: PenguinContext,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target = user or ctx.author

        async with (
            ctx.typing(),
            self.bot.chunithm_networks.network(
                ctx, target.id, kamaitachi=kamaitachi
            ) as client,
        ):
            if not client.SUPPORTS_PROFILE:
                msg = f"The network {client.NAME} does not support player profiles."
                raise commands.CommandError(msg)

            profile = await client.get_profile()

        async with self.bot.begin_db_session() as session:
            query = select(Cookie).where(Cookie.discord_id == target.id)
            cookie = (await session.execute(query)).scalar_one_or_none()

        view = ProfileView(
            ctx,
            target,
            profile,
            client.ACCENT_COLOR,
            is_supporter=cookie is not None and cookie.is_supporter,
            is_contributor=cookie is not None and cookie.is_contributor,
        )
        await view.start()

    @flags.command(name="chunithm", aliases=["chuni", "profile"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("user", nargs="?", default=None, type=MemberOrUserConverter)
    @logged_prefix_command
    async def chunithm(
        self,
        ctx: PenguinContext,
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
        interaction: discord.Interaction["ChuniBot"],
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

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

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(ctx, chunithm_net=True) as client,
        ):
            try:
                await client.update_username(new_name)
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

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(ctx, chunithm_net=True) as client,
        ):
            login_bonus = await client.get_login_bonus_progress()

        view = LoginBonusView(ctx, login_bonus)
        await view.start()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(ProfileCog(bot))
