import calendar
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, override

import discord
from discord.utils import MISSING, escape_markdown

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.networks.types import LoginBonus, LoginBonusItem

from ._pagination import ListPageSource, PaginationView
from .embeds import EmbedPageSource

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class LoginBonusItemPaginationSource(ListPageSource[LoginBonusItem]):
    def __init__(
        self,
        entries: list[LoginBonusItem],
        *,
        unobtained_color: discord.Color,
        per_page: int,
        days_logged_in: int = MISSING,
    ) -> None:
        super().__init__(entries, per_page=per_page)

        self.unobtained_color = unobtained_color
        self.days_logged_in = days_logged_in

    @override
    async def format_page(
        self, menu: "PaginationView", page: Sequence[LoginBonusItem]
    ) -> dict[str, Any]:
        embeds: list[discord.Embed] = []

        for item in page:
            color = self.unobtained_color
            description = f"**{escape_markdown(item.name)}**"

            if item.obtained:
                color = discord.Color.green()
                description += "\nObtained!"

            embed = discord.Embed(color=color, description=description)
            embed.set_author(name=f"DAY {item.day}")
            embed.set_thumbnail(url=item.icon_url)

            embeds.append(embed)

        result: dict[str, Any] = {"embeds": embeds}

        if self.days_logged_in is not MISSING and self.days_logged_in > 0:
            result["content"] = (
                f"You've logged in {self.days_logged_in} day{'s' if self.days_logged_in != 1 else ''} this month."
            )
        else:
            result["content"] = ""

        return result


class LoginBonusView(PaginationView):
    def __init__(self, ctx: PenguinContext, login_bonus: LoginBonus):
        self._login_bonus = login_bonus

        super().__init__(
            ctx,
            LoginBonusItemPaginationSource(
                login_bonus.monthly_login_bonus.rewards,
                unobtained_color=discord.Color.pink(),
                per_page=4,
                days_logged_in=login_bonus.monthly_login_bonus.days_logged_in,
            ),
        )
        self.add_item(self.monthly_login_bonus)
        self.add_item(self.login_bonus)
        self.add_item(self.daily_bonus)

        self.monthly_login_bonus.label = login_bonus.monthly_login_bonus.name

    def _highlight_selected_button(self, button: discord.ui.Button):
        self.monthly_login_bonus.style = discord.ButtonStyle.secondary
        self.login_bonus.style = discord.ButtonStyle.secondary
        self.daily_bonus.style = discord.ButtonStyle.secondary

        button.style = discord.ButtonStyle.green

    def _remove_pagination_buttons(self):
        self.remove_item(self.to_first_page)
        self.remove_item(self.to_previous_page)
        self.remove_item(self.to_next_page)
        self.remove_item(self.to_last_page)

    @override
    async def on_timeout(self) -> None:
        self.monthly_login_bonus.disabled = True
        self.login_bonus.disabled = True
        self.daily_bonus.disabled = True

        self._remove_pagination_buttons()

        if self.message is not None:
            await self.message.edit(view=self)

    @discord.ui.button(
        label="Monthly Login Bonus", row=2, style=discord.ButtonStyle.green
    )
    async def monthly_login_bonus(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        self._highlight_selected_button(button)
        self.source = LoginBonusItemPaginationSource(
            self._login_bonus.monthly_login_bonus.rewards,
            unobtained_color=discord.Color.pink(),
            per_page=4,
            days_logged_in=self._login_bonus.monthly_login_bonus.days_logged_in,
        )
        self._remove_pagination_buttons()
        self.fill_items()

        await self.show_page(interaction, 0)

    @discord.ui.button(label="Login Bonus", row=2)
    async def login_bonus(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        self._highlight_selected_button(button)
        self.source = LoginBonusItemPaginationSource(
            self._login_bonus.login_bonus,
            unobtained_color=discord.Color.blue(),
            per_page=4,
        )
        self._remove_pagination_buttons()
        self.fill_items()

        await self.show_page(interaction, 0)

    @discord.ui.button(label="Daily Bonus", row=2)
    async def daily_bonus(
        self, interaction: discord.Interaction["ChuniBot"], button: discord.ui.Button
    ):
        embed = discord.Embed(color=discord.Color.yellow(), title="Daily Bonus")
        description_parts: list[str] = []

        for daily_bonus in self._login_bonus.daily_bonus:
            weekday_emote = ":white_large_square:"

            if daily_bonus.weekday == calendar.SATURDAY:
                weekday_emote = ":blue_square:"
            elif daily_bonus.weekday == calendar.SUNDAY:
                weekday_emote = ":red_square:"

            bonus_emote = config.icons.icon(
                daily_bonus.icon_url.split("/")[-1].split(".")[0]
            )
            weekday_description = f"{weekday_emote} `{daily_bonus.weekday_name[:3]}.`"

            if bonus_emote is not None:
                weekday_description += f" {bonus_emote}"

            weekday_description += f" {daily_bonus.bonus}"

            if daily_bonus.is_today:
                weekday_description = f"**{weekday_description}**"

            description_parts.append(weekday_description)

        embed.description = "\n".join(description_parts)

        self._highlight_selected_button(button)
        self.source = EmbedPageSource(
            entries=[embed], per_page=1, with_page_marker=False
        )
        self._remove_pagination_buttons()

        await self.show_page(interaction, 0)
