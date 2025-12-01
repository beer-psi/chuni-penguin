import asyncio
import functools
import io
import re
from typing import TYPE_CHECKING, Any, override

import discord.ui
from discord import ButtonStyle, Interaction
from discord.ext import commands
from discord.utils import MISSING, escape_markdown
from PIL import Image

from chuni_penguin.context import PenguinContext
from chuni_penguin.networks.chunithm_net.exceptions import ChuniNetError
from chuni_penguin.networks.errors import AlreadyFriends, InvalidFriendCode
from chuni_penguin.networks.types import TeamEmblem

from ._base import PenguinView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.networks.types import Profile


async def handle_add_friend_interaction(
    interaction: Interaction["ChuniBot"],
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

    ctx = interaction.client.chunithm_networks.network(
        interaction, interaction.user.id, chunithm_net=True
    )

    try:
        client = await ctx.__aenter__()

        await client.send_friend_request(friend_code)

        embed.title = "Success"
        embed.description = f"Sent a friend request to {name}."
        embed.color = discord.Color.green()
    except AlreadyFriends:
        embed.description = "You've already sent this player a friend request, or you're already friends with this player."
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
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "This menu cannot be controlled by you, sorry!", ephemeral=True
        )
        return False

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
    async def callback(self, interaction: Interaction["ChuniBot"]):  # pyright: ignore[reportIncompatibleMethodOverride]
        await handle_add_friend_interaction(
            interaction,
            self.user_id,
            self.name,
            self.friend_code,
        )


class ProfileView(PenguinView):
    def __init__(
        self,
        ctx: PenguinContext,
        target: discord.abc.Snowflake,
        profile: "Profile",
        no_possession_color: int | discord.Color,
        *,
        timeout: float | None = 120,
        is_supporter: bool = False,
        is_contributor: bool = False,
    ):
        super().__init__(ctx, timeout=timeout)

        self.profile = profile
        self.no_possession_color = no_possession_color
        self.friend_code_visible = False
        self.send_friend_request_button = None
        self.is_supporter = is_supporter
        self.is_contributor = is_contributor

        if not self.profile.friend_code or ctx.author != target:
            self.clear_items()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        return True

    async def _before_start(self, *, content: str | None = None) -> dict[str, Any]:
        embed = discord.Embed(
            color=(
                self.profile.possession.color
                if self.profile.possession is not None
                else self.no_possession_color
            )
        )
        description_lines: list[str] = []

        if len(self.profile.titles) > 0:
            titles = "\n".join(
                [f"**{escape_markdown(t.content)}**" for t in self.profile.titles]
            )
            description_lines.append(titles)

            if self.profile.url is not None:
                description_lines.append(
                    f"### [{escape_markdown(self.profile.username)}]({self.profile.url})"
                )
            else:
                description_lines.append(
                    f"### {escape_markdown(self.profile.username)}"
                )
        else:
            embed.title = self.profile.username
            embed.url = self.profile.url

        if (team := self.profile.team) is not None:
            tag = (
                f"{team.emblem.value.capitalize()} Team"
                if team.emblem != TeamEmblem.normal
                else "Team"
            )

            description_lines.append(f"{tag} {escape_markdown(team.name)}")

        if self.profile.medal is not None:
            content = f"Class {self.profile.medal}"
            if self.profile.emblem is not None:
                content += f", cleared all of class {self.profile.emblem}"
            content += "."
            description_lines.append(content)

        if self.profile.level is not None:
            if (
                self.profile.reincarnation_stars is not None
                and self.profile.reincarnation_stars > 0
            ):
                level = f"{self.profile.reincarnation_stars}⭐ + {self.profile.level}"
            else:
                level = f"{self.profile.level}"

            description_lines.append(f"▸ **Level**: {level}")

        for rating_system in self.profile.rating_systems:
            content = f"▸ **{escape_markdown(rating_system.name)}**: {round(rating_system.value, 2):.2f}"

            if rating_system.max_value is not None:
                content += f" (MAX {rating_system.max_value})"

            description_lines.append(content)

        if self.profile.over_power is not None:
            description_lines.append(
                f"▸ **OVER POWER**: {self.profile.over_power.value:.2f} ({self.profile.over_power.percentage:.2f}%)"
            )

        if self.profile.total_credits is not None:
            description_lines.append(f"▸ **Credits**: {self.profile.total_credits}")

        if self.profile.total_scores is not None:
            description_lines.append(f"▸ **Scores**: {self.profile.total_scores}")

        for k, v in self.profile.extras.items():
            description_lines.append(f"▸ **{escape_markdown(k)}**: {v}")

        if self.profile.last_played is not None:
            description_lines.append(
                f"▸ **Last played**: <t:{int(self.profile.last_played.timestamp())}:f>"
            )

        embed.description = "\n".join(description_lines)

        if self.profile.banner is not None:
            embed.set_image(url=self.profile.banner)

        special_roles: list[str] = []

        if self.is_contributor:
            special_roles.append("contributor")
        if self.is_supporter:
            special_roles.append("supporter")

        if special_roles:
            if len(special_roles) >= 3:
                combined = f"{', '.join(special_roles[:-1])} and {special_roles[-1]}"
            else:
                combined = " and ".join(special_roles)

            embed.set_footer(
                text=f"This player is a chuni penguin {combined}. Thank you! :D"
            )

        files: list[discord.File] = MISSING

        if self.profile.profile_picture is not None:
            if self.profile.profile_picture_frame is None:
                embed.set_thumbnail(url=self.profile.profile_picture)
            else:
                character_resp, charaframe_resp = await asyncio.gather(
                    self.ctx.bot.caching_http_client.get(self.profile.profile_picture),
                    self.ctx.bot.caching_http_client.get(
                        self.profile.profile_picture_frame
                    ),
                )

                character = Image.open(io.BytesIO(character_resp.content))
                charaframe = Image.open(io.BytesIO(charaframe_resp.content))

                character = character.resize((87, 87), Image.Resampling.LANCZOS)
                charaframe = charaframe.resize((98, 98), Image.Resampling.LANCZOS)

                charaframe.paste(character, (6, 6), character)

                avatar = io.BytesIO()
                charaframe.save(avatar, "WEBP", optimize=True)
                avatar.seek(0)

                files = [discord.File(avatar, filename="avatar.webp")]
                embed.set_thumbnail(url="attachment://avatar.webp")

        return {"embed": embed, "files": files}

    @override
    async def on_timeout(self) -> None:
        if self.message is None:
            return

        if self.friend_code_visible and self.profile.friend_code is not None:
            persistent_view = discord.ui.View(timeout=None)
            persistent_view.add_item(PersistentHideFriendCodeButton(self.ctx.author.id))
            persistent_view.add_item(
                PersistentSendFriendRequestButton(
                    self.ctx.author.id, self.profile.friend_code, self.profile.username
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
        if not await super().interaction_check(interaction):
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
        self, interaction: Interaction["ChuniBot"], button: discord.ui.Button
    ):
        return await handle_add_friend_interaction(
            interaction,
            self.ctx.author.id,
            self.profile.username,
            self.profile.friend_code,
        )
