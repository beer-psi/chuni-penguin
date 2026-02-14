import calendar
from collections.abc import Sequence
from typing import TYPE_CHECKING, override

import discord
from discord.utils import MISSING, escape_markdown

from chuni_penguin.config import config
from chuni_penguin.context import PenguinContext
from chuni_penguin.networks.types import LoginBonus, LoginBonusItem

from ._pagination import FormatPageReturn, ListPageSource, PaginationView
from .embeds import EmbedPageSource

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot


class LoginBonusItemPaginationSource(ListPageSource[LoginBonusItem]):
    __slots__ = ("days_logged_in", "unobtained_color")

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
    ) -> FormatPageReturn:
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

        result: FormatPageReturn = {"embeds": embeds}

        if self.days_logged_in is not MISSING and self.days_logged_in > 0:
            result["content"] = (
                f"You've logged in {self.days_logged_in} day{'s' if self.days_logged_in != 1 else ''} for this event."
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
                login_bonus.monthly_login_bonus[0].rewards,
                unobtained_color=discord.Color.pink(),
                per_page=4,
                days_logged_in=login_bonus.monthly_login_bonus[0].days_logged_in,
            ),
        )

        self.select_login_bonus.options = [
            discord.SelectOption(label=monthly_bonus.name, value=monthly_bonus.name)
            for monthly_bonus in login_bonus.monthly_login_bonus
        ]
        self.select_login_bonus.options.append(
            discord.SelectOption(label="Login Bonus", value="login")
        )
        self.select_login_bonus.options.append(
            discord.SelectOption(label="Daily Bonus", value="daily")
        )

        self.select_login_bonus.options[0].default = True

        self.add_item(self.select_login_bonus)

    def _remove_pagination_buttons(self):
        self.remove_item(self.to_first_page)
        self.remove_item(self.to_previous_page)
        self.remove_item(self.jump_to_page)
        self.remove_item(self.to_next_page)
        self.remove_item(self.to_last_page)

    @override
    async def on_timeout(self) -> None:
        self.select_login_bonus.disabled = True

        self._remove_pagination_buttons()

        if self.message is not None:
            await self.message.edit(view=self)

    @property
    def _selected_value(self):
        try:
            return self.select_login_bonus.values[0]  # pyright: ignore[reportAttributeAccessIssue]
        except IndexError:
            try:
                return next(
                    option.value
                    for option in self.select_login_bonus.options  # pyright: ignore[reportAttributeAccessIssue]
                    if option.default
                )
            except StopIteration:
                return self.select_login_bonus.options[0].value  # pyright: ignore[reportAttributeAccessIssue]

    def _get_pagination_source(self):
        selected_value = self._selected_value

        if selected_value == "login":
            return LoginBonusItemPaginationSource(
                self._login_bonus.login_bonus,
                unobtained_color=discord.Color.blue(),
                per_page=4,
            )

        if selected_value == "daily":
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
                weekday_description = (
                    f"{weekday_emote} `{daily_bonus.weekday_name[:3]}.`"
                )

                if bonus_emote is not None:
                    weekday_description += f" {bonus_emote}"

                weekday_description += f" {daily_bonus.bonus}"

                if daily_bonus.is_today:
                    weekday_description = f"**{weekday_description}**"

                description_parts.append(weekday_description)

            embed.description = "\n".join(description_parts)

            return EmbedPageSource(entries=[embed], per_page=1)

        monthly_login_bonus = next(
            b for b in self._login_bonus.monthly_login_bonus if b.name == selected_value
        )
        return LoginBonusItemPaginationSource(
            monthly_login_bonus.rewards,
            unobtained_color=discord.Color.pink(),
            per_page=4,
            days_logged_in=monthly_login_bonus.days_logged_in,
        )

    @discord.ui.select(
        placeholder="Select a login bonus...",
        options=[
            discord.SelectOption(
                label="Monthly Login Bonus", value="monthly", default=True
            ),
            discord.SelectOption(label="Login Bonus", value="login"),
            discord.SelectOption(label="Daily Bonus", value="daily"),
        ],
        row=2,
    )
    async def select_login_bonus(
        self, interaction: discord.Interaction["ChuniBot"], select: discord.ui.Select
    ):
        selected_value = self._selected_value

        for option in select.options:
            option.default = option.value == selected_value

        self.source = self._get_pagination_source()

        self._remove_pagination_buttons()

        if selected_value != "daily":
            self.fill_items()

        await self.show_page(interaction, 0)
