import contextlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self, overload, override

import discord
from discord.ext import commands
from discord.ext.track_edits import EditTrackableContext
from discord.utils import MISSING, escape_markdown
from discord.webhook.async_ import WebhookMessage
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chunithm_net.models.enums import Difficulty
from database.models import Chart, UserConfig
from utils import did_you_mean_text
from utils.constants import SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    # it's literally used i don't know why ruff tripped on this one
    from bot import ChuniBot


class PenguinContext(EditTrackableContext["ChuniBot"]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.response: discord.Message | None = None
        self.user_config: UserConfig = MISSING

    @override
    async def reply(self, content: str | None = None, **kwargs: Any) -> discord.Message:
        # Ensure that if the original message was deleted somewhere in-between, we can still
        # safely put out the response

        try:
            msg = await super().reply(content, **kwargs)
        except discord.errors.HTTPException:
            msg = await self.send(content, **kwargs)

        self.response = msg

        return msg

    @classmethod
    async def from_interaction(
        cls, interaction: discord.Interaction["ChuniBot"], /
    ) -> Self:
        ctx = await super().from_interaction(interaction)
        ctx.user_config = await interaction.client.utils.fetch_user_config(
            interaction.user.id
        )

        return ctx

    @overload
    async def respond_or_edit(
        self,
        content: str | None = ...,
        *,
        embed: discord.Embed = ...,
        files: Sequence[discord.File] = ...,
        suppress_embeds: bool = ...,
        delete_after: float | None = ...,
        allowed_mentions: discord.AllowedMentions = ...,
        view: discord.ui.View | None = ...,
        ephemeral: bool = ...,
    ) -> discord.Message: ...

    @overload
    async def respond_or_edit(
        self,
        content: str | None = ...,
        *,
        embeds: Sequence[discord.Embed] = ...,
        files: Sequence[discord.File] = ...,
        suppress_embeds: bool = ...,
        delete_after: float | None = ...,
        allowed_mentions: discord.AllowedMentions = ...,
        view: discord.ui.View | None = ...,
        ephemeral: bool = ...,
    ) -> discord.Message: ...

    async def respond_or_edit(
        self, content: str | None = None, **kwargs: Any
    ) -> discord.Message:
        """Reply to the message referenced by this context, or update
        the response if we've replied before."""

        kwargs.pop("mention_author", None)

        if self.response is not None:
            edit_kwargs = {
                "content": content,
                "embed": kwargs.get("embed", MISSING),
                "embeds": kwargs.get("embeds", MISSING),
                "attachments": kwargs.get("files", MISSING),
                "view": kwargs.get("view", MISSING),
                "allowed_mentions": kwargs.get("allowed_mentions", MISSING),
            }

            if isinstance(self.response, discord.InteractionMessage):
                edit_kwargs["delete_after"] = kwargs.get("delete_after")
            elif not isinstance(self.response, WebhookMessage):
                edit_kwargs["suppress"] = kwargs.get("suppress_embeds", False)
                edit_kwargs["delete_after"] = kwargs.get("delete_after")

            with contextlib.suppress(discord.errors.NotFound):
                self.response = await self.response.edit(**edit_kwargs)

                return self.response

        return await self.reply(content=content, mention_author=False, **kwargs)

    async def find_chart(
        self,
        difficulty: Difficulty,
        query: str,
        select_prompt: str = "Select a chart:",
    ) -> Chart | None:
        """Finds a chart with the given difficulty and query, prompting the user if there are multiple
        options.

        Returns a 2-tuple, where the first item is the select message sent if the user was prompted, and
        the second item is the chart.
        """

        from chuni_penguin.ui.confirmation import ConfirmationYesView
        from chuni_penguin.ui.select_to_compare import SelectToCompareView

        guild_id = self.guild.id if self.guild else None
        result = await self.bot.utils.find_songs(query, guild_id=guild_id)

        if result.similarity < SIMILARITY_THRESHOLD:
            view = ConfirmationYesView(self)
            msg = did_you_mean_text(self.prefix, result.songs[0], result.matched_alias)

            await view.start(content=msg)
            await view.wait()

            if not view.result:
                return None

        song_ids = {s.id for s in result.songs}

        async with self.bot.begin_db_session() as session:
            stmt = (
                select(Chart)
                .where(
                    (Chart.song_id.in_(song_ids))
                    & (Chart.difficulty == difficulty.short_form())
                )
                .options(joinedload(Chart.song), joinedload(Chart.sdvxin_chart_view))
            )
            charts = (await session.execute(stmt)).scalars().all()

        if len(charts) == 0:
            msg = f"No charts found for {escape_markdown(result.songs[0].title)} [{difficulty}]."
            raise commands.CommandError(msg)

        if len(charts) == 1:
            return charts[0]

        view = SelectToCompareView(
            self,
            [
                (
                    f"{x.song.title} [{Difficulty.from_short_form(x.difficulty)} {x.const or x.level}]",
                    i,
                )
                for i, x in enumerate(charts)
            ],
            placeholder="Select a chart...",
        )
        await self.respond_or_edit(select_prompt, view=view)

        await view.wait()

        if view.value is None:
            msg = "Timed out before selecting a chart."
            raise commands.CommandError(msg)

        return charts[int(view.value)]


class PenguinGuildContext(PenguinContext):
    """Utility context class used when we know that we're in a Discord guild; for instance,
    when using @commands.guild_only()."""

    author: discord.Member  # pyright: ignore[reportIncompatibleVariableOverride]
    guild: discord.Guild  # pyright: ignore[reportIncompatibleVariableOverride]
    channel: discord.VoiceChannel | discord.TextChannel | discord.Thread  # pyright: ignore[reportIncompatibleVariableOverride]
    me: discord.Member  # pyright: ignore[reportIncompatibleVariableOverride]
    prefix: str  # pyright: ignore[reportIncompatibleVariableOverride]
