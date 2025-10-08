import itertools
from typing import TYPE_CHECKING, Any, AsyncContextManager, override

import discord.ui
from discord.ext.commands import Context

from chuni_penguin.ui import ScoreCardEmbed

from ._pagination import ListPageSource, PaginationView

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.botutils import UtilsCog
    from chuni_penguin.networks.base import Network
    from chuni_penguin.networks.types import Profile, RecentScore


def split_scores_into_credits(
    scores: list["RecentScore"],
) -> list[list["RecentScore"]]:
    if any(s.track_no is None for s in scores):
        return [list(c) for c in itertools.batched(scores, 3)]

    credits = []
    current_credit = [scores[0]]
    last_track = scores[0].track_no

    for score in scores[1:]:
        assert score.track_no is not None
        assert last_track is not None

        if score.track_no >= last_track:
            credits.append(current_credit)
            current_credit = []
        current_credit.append(score)
        last_track = score.track_no

    if len(current_credit) > 0:
        credits.append(current_credit)

    return credits


class RecentRecordsPageSource(ListPageSource[list["RecentScore"]]):
    def __init__(
        self,
        records: list["RecentScore"],
        *,
        synthesis_alt_jacket: str | None = None,
    ) -> None:
        super().__init__(split_scores_into_credits(records), per_page=1)

        self.synthesis_alt_jacket = synthesis_alt_jacket

    @override
    async def format_page(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, menu: "PaginationView", page: list[list["RecentScore"]]
    ) -> dict[str, Any]:
        scores = page[0]
        embeds: list[discord.Embed] = [
            ScoreCardEmbed(s, synthesis_alt_jacket=self.synthesis_alt_jacket)
            for s in scores
        ]
        embeds.append(
            discord.Embed(
                description=f"Page {menu.current_page + 1}/{self.get_max_pages()}",
            )
        )

        return {"embeds": embeds}


class RecentRecordsView(PaginationView):
    def __init__(
        self,
        ctx: Context,
        bot: "ChuniBot",
        scores: list["RecentScore"],
        network_client: "Network",
        network_client_manager: AsyncContextManager["Network"],
        userinfo: "Profile",
        synthesis_alt_jacket: str | None = None,
    ):
        super().__init__(
            ctx,
            source=RecentRecordsPageSource(
                scores, synthesis_alt_jacket=synthesis_alt_jacket
            ),
        )
        self.add_item(self.switch_to_26_50)
        self.add_item(self.dropdown)

        self.scores = scores
        self.network_client = network_client
        self.network_client_manager: AsyncContextManager["Network"] | None = (
            network_client_manager
        )
        self.userinfo = userinfo
        self.synthesis_alt_jacket = synthesis_alt_jacket

        self.utils: "UtilsCog" = bot.utils

        self._dropdown_options = [
            discord.SelectOption(
                label=f"{idx + 1}. {score.title} - {score.difficulty}",
                value=f"{idx}",
            )
            for (idx, score) in enumerate(scores)
        ]
        self.dropdown.options = self._dropdown_options[:25]

    async def _before_start(self, *, content: str | None = None):
        if not self.network_client.SUPPORTS_DETAILED_RECENT_SCORE:
            self.clear_items()

            if self.network_client_manager is not None:
                await self.network_client_manager.__aexit__(None, None, None)

            self.network_client_manager = None

        return await super()._before_start(content=content)

    async def on_timeout(self):
        if self.network_client_manager is not None:
            await self.network_client_manager.__aexit__(None, None, None)

        return await super().on_timeout()

    @discord.ui.button(label="26-50")
    async def switch_to_26_50(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if button.label == "26-50":
            self.dropdown.options = self._dropdown_options[25:]
            button.label = "1-25"
        else:
            self.dropdown.options = self._dropdown_options[:25]
            button.label = "26-50"

        await interaction.response.edit_message(view=self)

    if TYPE_CHECKING:
        dropdown: discord.ui.Select
    else:

        @discord.ui.select(placeholder="Select a score", row=1)
        async def dropdown(
            self, interaction: discord.Interaction, select: discord.ui.Select
        ):
            if not isinstance(interaction.channel, discord.abc.Messageable):
                return
            await interaction.response.defer()

            idx = int(select.values[0])
            score = await self.network_client.detailed_recent_record(self.scores[idx])
            score = await self.utils.hydrate_record(score)

            if interaction.message is not None:
                await interaction.message.edit(
                    content=f"Score of {self.userinfo.name}",
                    embed=ScoreCardEmbed(
                        score, synthesis_alt_jacket=self.synthesis_alt_jacket
                    ),
                    view=self,
                )
            else:
                await interaction.channel.send(
                    content=f"Score of {self.userinfo.name}",
                    embed=ScoreCardEmbed(
                        score, synthesis_alt_jacket=self.synthesis_alt_jacket
                    ),
                    view=self,
                )
