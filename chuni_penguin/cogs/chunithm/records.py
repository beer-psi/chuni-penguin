# ruff: noqa: E731
import asyncio
import contextlib
import itertools
import math
import random
import statistics
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chuni_penguin import flags
from chuni_penguin.adapters.chunithm_net import ChunithmNetAdapter
from chuni_penguin.adapters.errors import ChartNotFound, NetworkError, SongNotFound
from chuni_penguin.adapters.kamaitachi import KamaitachiAdapter
from chuni_penguin.adapters.utils import calculate_ongeki_rating_breakdown
from chuni_penguin.calculation.overpower import (
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
)
from chuni_penguin.config import config
from chuni_penguin.constants import (
    CACHE_DIR,
    CURRENT_CHUNITHM_VERSION,
    INTERNATIONAL_JACKET_BASE,
    JACKET_BASE,
    ChunithmVersion,
)
from chuni_penguin.context import PenguinContext
from chuni_penguin.converters import (
    AliasNameConverter,
    AliasNameTransformer,
    DifficultyConverter,
    GenreConverter,
    Level,
    LevelConverter,
    LevelRange,
    LevelRangeConverter,
    MemberOrUserConverter,
    RankConverter,
    RankingDifficultyConverter,
    VersionConverter,
)
from chuni_penguin.database import Chart, Song, SongJacket, UserConfig
from chuni_penguin.database import PersonalBest as DBPersonalBest
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.renderers.b50 import render_b30
from chuni_penguin.renderers.b50_ongeki import render_b30 as render_b30_ongeki
from chuni_penguin.types import (
    ClearLamp,
    ComboLamp,
    Difficulty,
    Genre,
    PersonalBest,
    Possession,
    Profile,
    Rank,
    RatingBreakdown,
    RatingFrameType,
    RatingType,
    Score,
)
from chuni_penguin.types.ranking import RankingType
from chuni_penguin.ui import (
    B30N20View,
    B30View,
    EmbedPaginationView,
    FriendCodeOfferView,
    LeaderboardView,
    RecentRecordsView,
    ScoreCardEmbed,
    SelectToCompareView,
)
from chuni_penguin.ui.ranking import (
    CurrencyRankingView,
    RatingRankingView,
    ScoreRankingView,
    TeamRankingView,
)
from chuni_penguin.utils import TOKYO_TZ, AsyncTemporaryFile, floor_to_ndp
from chuni_penguin.utils.formatting import bold, bold_if
from chuni_penguin.utils.misc import Reversor

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot
    from chuni_penguin.cogs.autocompleters import AutocompletersCog


def _extract_images_from_component(
    component: discord.components.Component, url_whitelist: list[str] | None = None
):
    image_urls: list[str] = []

    if isinstance(component, discord.components.ThumbnailComponent) and (
        url_whitelist is None
        or any(url in component.media.url for url in url_whitelist)
    ):
        image_urls.append(component.media.url)

    if isinstance(component, discord.components.MediaGalleryComponent):
        image_urls.extend(
            [
                item.media.url
                for item in component.items
                if url_whitelist is None
                or any(url in item.media.url for url in url_whitelist)
            ]
        )

    if isinstance(component, discord.components.SectionComponent):
        image_urls.extend(
            _extract_images_from_component(component.accessory, url_whitelist)
        )

    if isinstance(component, discord.components.Container):
        image_urls.extend(
            itertools.chain.from_iterable(
                [
                    _extract_images_from_component(child, url_whitelist)
                    for child in component.children
                ]
            )
        )

    return image_urls


def _extract_images_from_message(
    message: discord.Message, url_whitelist: list[str] | None = None
):
    image_urls: list[str] = []

    embeds = message.embeds.copy()
    components = message.components.copy()

    for snapshot in message.message_snapshots:
        embeds.extend(snapshot.embeds)
        components.extend(snapshot.components)

    image_urls.extend(
        [
            embed.thumbnail.url
            for embed in embeds
            if embed.thumbnail.url is not None
            and (
                url_whitelist is None
                or any(url in embed.thumbnail.url for url in url_whitelist)
            )
        ]
    )
    image_urls.extend(
        itertools.chain.from_iterable(
            _extract_images_from_component(component, url_whitelist)
            for component in components
        )
    )

    return image_urls


class RecordsCog(commands.Cog, name="Records"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot
        self.utils = self.bot.utils
        self.autocompleters: "AutocompletersCog" = self.bot.get_cog("Autocompleters")  # type: ignore[reportGeneralTypeIssues]

        self.compare_context_menu = app_commands.ContextMenu(
            name="View your score", callback=self.compare_context_menu_callback
        )

        self._random = random.Random()

    async def cog_load(self) -> None:
        (CACHE_DIR / "b50").mkdir(parents=True, exist_ok=True)
        self.bot.tree.add_command(self.compare_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.compare_context_menu.name, type=self.compare_context_menu.type
        )

    async def _recent_inner(
        self,
        ctx: PenguinContext,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id
        client_manager = ctx.bot.chunithm_networks.network(
            ctx, target_id, kamaitachi=kamaitachi
        )
        client = await client_manager.__aenter__()

        async with ctx.typing():
            profile = await client.get_minimal_profile()

            recents = await client.get_recent_scores()

        view = RecentRecordsView(
            ctx,
            target_id,
            recents,
            client,
            client_manager,
            profile,
            ctx.user_config.synthesis_alt_jacket,
        )
        await view.start(
            content=f"Most recent scores for {profile.username} on {client.NAME}:"
        )

    @flags.command("recent", aliases=["rs"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("user", nargs="?", default=None, type=MemberOrUserConverter)
    @logged_prefix_command
    async def recent(
        self,
        ctx: PenguinContext,
        *,
        kamaitachi: bool = False,
        user: discord.Member | discord.User | None = None,
    ):
        """View your recent scores.

        **Parameters**:
        `user`: The user to get scores for.
        `-k, --kamaitachi`: Get recent scores from Kamaitachi, if the user has that linked.
        """

        await self._recent_inner(ctx, user, kamaitachi=kamaitachi)

    @app_commands.command(name="recent", description="View recent scores")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to get recent scores for",
        kamaitachi="Get recent scores from Kamaitachi, if linked",
    )
    @logged_app_command
    async def recent_slash(
        self,
        interaction: Interaction["ChuniBot"],
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

        return await self._recent_inner(ctx, user, kamaitachi=kamaitachi)

    async def _compare_from_message(
        self,
        ctx: PenguinContext,
        message: discord.Message,
        message_images: list[str] | None = None,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        if message_images is None:
            message_images = _extract_images_from_message(message)

        if len(message_images) == 0:
            msg = "The message replied to does not contain any charts/scores."
            raise commands.BadArgument(msg)

        embeds = message.embeds.copy()
        containers = [
            component
            for component in message.components
            if isinstance(component, discord.components.Container)
        ]

        for snapshot in message.message_snapshots:
            embeds.extend(snapshot.embeds)
            containers.extend(
                [
                    component
                    for component in snapshot.components
                    if isinstance(component, discord.components.Container)
                ]
            )

        target_id = user.id if user is not None else ctx.author.id

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            async with self.bot.begin_db_read() as session:
                sql = (
                    select(SongJacket)
                    .where(SongJacket.jacket_url.in_(message_images))
                    .group_by(SongJacket.song_id)
                    .options(joinedload(SongJacket.song).joinedload(Song.charts))
                )
                jackets = (await session.execute(sql)).scalars().unique().all()

            if len(jackets) == 0:
                msg = "No songs found."
                raise commands.CommandError(msg)

            if len(jackets) > 1:
                options = []

                for i, jacket in enumerate(jackets):
                    displayed_option = jacket.song.title

                    if jacket.song.id >= 8000:
                        displayed_option += f" [{jacket.song.charts[0].level}]"

                    options.append((displayed_option, i))

                view = SelectToCompareView(ctx, options)
                await ctx.respond_or_edit("Select a score to compare with:", view=view)

                await view.wait()

                if view.value is None:
                    await ctx.respond_or_edit(
                        content="Timed out before selecting a score.", view=None
                    )
                    return

                jacket = jackets[int(view.value)]
                song = jacket.song
            else:
                jacket = jackets[0]
                song = jacket.song

            if isinstance(client, ChunithmNetAdapter):
                song.raise_if_not_available()

            if isinstance(client, KamaitachiAdapter) and song.genre == "WORLD'S END":
                msg = "Kamaitachi does not support WORLD'S END charts."
                raise commands.CommandError(msg)

            displayed_song = escape_markdown(song.title)

            if song.id >= 8000 and len(song.charts) > 0:
                displayed_song += f" [{escape_markdown(song.charts[0].level)}]"

            try:
                records = await client.get_personal_bests_on_song(song.id)
            except (SongNotFound, ChartNotFound):
                msg = (
                    f"The song **{displayed_song}** is not available on {client.NAME}."
                )
                raise commands.CommandError(msg) from None
            except NotImplementedError:
                msg = f"Network {client.NAME} does not support fetching scores for a specific song."
                raise commands.CommandError(msg) from None

            profile = await client.get_minimal_profile()

            if len(records) == 0:
                await ctx.respond_or_edit(
                    f"No records found for {profile.username} on **{displayed_song}**."
                )
                return

            records.sort(key=lambda r: r.chart.difficulty.value)

            page = 0
            embed_color = 0

            try:
                selected_embed = next(
                    x
                    for x in embeds
                    if jacket.jacket_url in {x.thumbnail.url, x.image.url}
                )
                embed_color = (
                    selected_embed.color.value
                    if selected_embed.color is not None
                    else 0
                )
            except StopIteration:
                for c in containers:
                    if jacket.jacket_url in _extract_images_from_component(c):
                        embed_color = (
                            c.accent_color.value if c.accent_color is not None else 0
                        )
                        break

            with contextlib.suppress(ValueError):
                # embed_color may exist with invalid value
                difficulty = Difficulty.from_embed_color(embed_color)
                page = next(
                    (
                        i
                        for i, record in enumerate(records)
                        if record.chart.difficulty == difficulty
                    ),
                    0,
                )

            view = EmbedPaginationView(
                ctx,
                [
                    ScoreCardEmbed(
                        r,
                        synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                        detailed=True,
                    )
                    for r in records
                ],
            )
            view.current_page = page
            content = f"Top play for {profile.username} on {client.NAME}:"

        if ctx.response is not None:
            await view.start_from(ctx.response, content=content)
        else:
            await view.start(content=content)

    async def _compare_inner(
        self,
        ctx: PenguinContext,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        url_whitelist = [JACKET_BASE, INTERNATIONAL_JACKET_BASE]
        image_urls_by_message: dict[int, list[str]] = {}

        if config.web.serve_assets and config.web.base_url:
            url_whitelist.append(config.web.base_url)

        if (message := await ctx.resolve_message_reference()) is None:
            try:

                def check(m: discord.Message):
                    nonlocal url_whitelist
                    nonlocal image_urls_by_message

                    if m.author != self.bot.user:
                        return False

                    image_urls = _extract_images_from_message(m, url_whitelist)
                    image_urls_by_message[m.id] = image_urls

                    return len(image_urls) > 0

                message = await discord.utils.find(check, ctx.channel.history(limit=50))
            except discord.errors.Forbidden as e:
                msg = "Bot requires the Read Message History permission to fetch recent scores."

                if ctx.interaction is None:
                    msg += f" Alternatively, run `{ctx.clean_prefix}compare` while replying to the score you want to compare."

                raise commands.CheckFailure(msg) from e

            if message is None:
                msg = "No recent scores found."
                raise commands.CommandError(msg)

        await self._compare_from_message(
            ctx,
            message,
            image_urls_by_message.get(message.id),
            user,
            kamaitachi=kamaitachi,
        )

    @flags.command("compare", aliases=["c", "mog", "gap"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("user", nargs="?", default=None, type=MemberOrUserConverter)
    @logged_prefix_command
    async def compare(
        self,
        ctx: PenguinContext,
        *,
        kamaitachi: bool = False,
        user: discord.Member | discord.User | None = None,
    ):
        """Compare your best score with another score.

        By default, it's the most recently posted score. You can reply to another
        user's score to compare with that instead. If there are multiple scores in
        said message, you will be prompted to select one.

        **Tip**: This command also works with some other bots (<@986651489529397279> and <@604641359416131585>
        to name a few). However, you will need to explicitly reply to those other bots' messages.
        If you don't reply, only recent scores *from this bot* will be checked.

        **Parameters**
        `user`: The user to compare with (defaults to you).
        `-k, --kamaitachi`: Get scores from Kamaitachi, if the target user has a linked account.
        """

        await self._compare_inner(ctx, user, kamaitachi=kamaitachi)

    @app_commands.command(
        name="compare", description="Compare your best score with another score."
    )
    @app_commands.describe(
        user="The user to compare with (defaults to you)",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account",
    )
    @logged_app_command
    async def compare_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

        await self._compare_inner(ctx, user, kamaitachi=kamaitachi)

    async def compare_context_menu_callback(
        self, interaction: discord.Interaction["ChuniBot"], message: discord.Message
    ):
        await self._compare_from_message(
            await PenguinContext.from_interaction(interaction), message
        )

    async def song_title_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.autocompleters.song_title_autocomplete(interaction, current)

    async def _scores_inner(
        self,
        ctx: PenguinContext,
        query: str,
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            result = await ctx.find_songs(query, load_charts=True)

            if result is None:
                return

            # if we're fetching scores from Kamaitachi, we don't need to care about whether
            # the song is available in CHUNITHM International.
            #
            # However, we need to keep in mind that Kamaitachi does not support WORLD'S END.
            songs = [
                x
                for x in result.songs
                if (isinstance(client, KamaitachiAdapter) and x.genre != "WORLD'S END")
                or (isinstance(client, ChunithmNetAdapter) and x.available)
            ]

            if len(songs) > 1:
                options = []

                for i, x in enumerate(songs):
                    if x.genre == "WORLD'S END":
                        title = f"{x.title} [{x.charts[0].level}]"
                    else:
                        title = x.title

                    options.append((title, i))
                view = SelectToCompareView(
                    ctx, options=options, placeholder="Select a song..."
                )
                await ctx.respond_or_edit(
                    "Multiple songs were found. Select one:", view=view
                )

                await view.wait()

                if view.value is None:
                    await ctx.respond_or_edit(
                        content="Timed out before selecting a song.", view=None
                    )
                    return

                song = songs[int(view.value)]
            elif len(songs) > 0:
                song = songs[0]
            else:
                msg = f"No songs currently available in CHUNITHM International matches the query. Closest match was **{escape_markdown(result.songs[0].title)}**."
                raise commands.BadArgument(msg)

            displayed_song = escape_markdown(song.title)

            if song.id >= 8000 and len(song.charts) > 0:
                displayed_song += f" [{escape_markdown(song.charts[0].level)}]"

            profile = await client.get_minimal_profile()

            try:
                records = await client.get_personal_bests_on_song(song.id)
            except (SongNotFound, ChartNotFound):
                msg = f"The song **{escape_markdown(song.title)}** is not available on {client.NAME}."
                raise commands.CommandError(msg) from None

            if len(records) == 0:
                msg = f"No records found for {profile.username} on **{displayed_song}** on {client.NAME}."

                await ctx.respond_or_edit(msg)
                return

            records.sort(key=lambda r: r.chart.difficulty.value)

            view = EmbedPaginationView(
                ctx,
                [
                    ScoreCardEmbed(
                        r,
                        synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                        detailed=True,
                    )
                    for r in records
                ],
            )
            content = f"Top play for {profile.username} on {client.NAME}:"

        if ctx.response is not None:
            await view.start_from(ctx.response, content=content)
        else:
            await view.start(content=content)

    @flags.command("scores", aliases=["score"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument(
        "user",
        nargs=flags.OPTIONAL_INVISIBLE,
        default=None,
        type=MemberOrUserConverter,
    )
    @flags.argument("query", nargs="*")
    @logged_prefix_command
    async def scores(
        self,
        ctx: PenguinContext,
        *,
        kamaitachi: bool = False,
        user: discord.Member | discord.User | None = None,
        query: list[str] | None = None,
    ):
        """Get a player's scores for a specific song.

        **Parameters**:
        `user` (not required): The user to get scores for. Must go first if specified.
        `query` (required): The song to search for. You don't have to be exact; try things out!
        `-k, --kamaitachi`: Get scores from Kamaitachi, if the user has that linked.
        """

        if query is None or len(query) <= 0:
            await self._compare_inner(ctx, user=user, kamaitachi=kamaitachi)
            return

        _query = await AliasNameConverter(lower=True).convert(ctx, " ".join(query))

        await self._scores_inner(ctx, query=_query, user=user, kamaitachi=kamaitachi)

    @app_commands.command(
        name="scores",
        description="Get personal bests for a specific song",
    )
    @app_commands.describe(
        query="The song to search for. You don't have to be exact; try things out!",
        user="The user to get scores for.",
        kamaitachi="Get scores from Kamaitachi, if the user has that linked.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_app_command
    async def scores_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        query: app_commands.Transform[str, AliasNameTransformer(lower=True)],
        user: discord.User | discord.Member | None = None,
        *,
        kamaitachi: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

        await self._scores_inner(ctx, query, user, kamaitachi=kamaitachi)

    async def _best50_ongeki(
        self,
        ctx: PenguinContext,
        profile: Profile,
        rating_breakdown: RatingBreakdown,
        user_config: UserConfig | None = None,
    ):
        current_rating = float(rating_breakdown.rating)
        records = rating_breakdown.frames[RatingFrameType.best].scores
        record_slots = rating_breakdown.frames[RatingFrameType.best].num_scores
        platinum_records = rating_breakdown.frames[RatingFrameType.platinum].scores
        platinum_record_slots = rating_breakdown.frames[
            RatingFrameType.platinum
        ].num_scores

        if (new_frame := rating_breakdown.frames.get(RatingFrameType.new)) is not None:
            new_records = new_frame.scores
            new_record_slots = new_frame.num_scores
        else:
            new_records = None
            new_record_slots = 0

        async with AsyncTemporaryFile() as f:
            await asyncio.to_thread(
                render_b30_ongeki,
                player_name=profile.username,
                output=f,
                records=records,
                record_slots=record_slots,
                new_records=new_records,
                new_record_slots=new_record_slots,
                platinum_records=platinum_records,
                platinum_record_slots=platinum_record_slots,
                current_rating=current_rating,
                user_config=user_config or ctx.user_config,
            )

            generation_timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")

            await ctx.respond_or_edit(
                files=[
                    discord.File(
                        f,
                        filename=f"chuni-penguin-b50-{profile.username}-{generation_timestamp}.png",
                    )
                ],
            )

    async def _best50_from_friend_code(
        self,
        ctx: PenguinContext,
        friend_code: str,
        *,
        classic: bool = False,
        rating_system: Literal["naive", "ingame", "ongeki", "ongeki-naive"]
        | None = None,
    ):
        pbs: list[PersonalBest] = []
        records: list[PersonalBest] = []
        record_slots: int = 30
        new_records: list[PersonalBest] | None = None
        new_record_slots: int = 20

        async with ctx.typing():
            (
                profile,
                pbs,
            ) = await ctx.bot.chunithm_networks.fetch_chunithm_net_from_friend_code(
                ctx, friend_code
            )

        pbs.sort(
            key=lambda pb: (
                pb.rating,
                pb.score,
                pb.combo_lamp,
                pb.chart.internal_level,
            ),
            reverse=True,
        )

        if rating_system == "naive":
            records = pbs[:50]
            record_slots = 50
            new_records = None
            new_record_slots = 0
            current_rating = None
        elif rating_system in ("ongeki", "ongeki-naive"):
            breakdown = calculate_ongeki_rating_breakdown(
                RatingType.ongeki
                if rating_system == "ongeki"
                else RatingType.ongeki_naive,
                pbs,
            )
            await self._best50_ongeki(ctx, profile, breakdown, ctx.user_config)
            return
        else:
            new_records = []
            current_rating = profile.rating_systems[0].value

            for pb in pbs:
                if (
                    pb.song.version == CURRENT_CHUNITHM_VERSION
                    and len(new_records) < new_record_slots
                ):
                    new_records.append(pb)

                if (
                    pb.song.version != CURRENT_CHUNITHM_VERSION
                    and len(records) < record_slots
                ):
                    records.append(pb)

                if (
                    len(records) >= record_slots
                    and len(new_records) >= new_record_slots
                ):
                    break

        async with ctx.typing():
            await self._best50_respond(
                ctx,
                profile,
                ctx.user_config,
                current_rating,
                records,
                record_slots,
                new_records,
                new_record_slots,
                classic=classic,
            )

    async def _best50_inner(
        self,
        ctx: PenguinContext,
        user: discord.User | discord.Member | None = None,
        *,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
        rating_system: Literal["naive", "ingame", "ongeki", "ongeki-naive"]
        | None = None,
    ):
        target_id = ctx.author.id if user is None else user.id
        cookie = await self.bot.database.cookies.get_by_discord_id(target_id)

        if (
            user is None
            and not kamaitachi
            and (
                cookie is None
                or (not cookie.cookie and cookie.kamaitachi_token is None)
            )
        ):
            view = FriendCodeOfferView(
                ctx, cookie.friend_code if cookie is not None else None
            )
            await view.start()
            return

        rating_type = None

        if rating_system == "ingame":
            rating_type = RatingType.in_game
        elif rating_system == "naive":
            rating_type = RatingType.naive
        elif rating_system == "ongeki":
            rating_type = RatingType.ongeki
        elif rating_system == "ongeki-naive":
            rating_type = RatingType.ongeki_naive
        elif rating_system is not None:
            msg = f"Unknown rating system {rating_system}"
            raise commands.BadArgument(msg)

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            user_config = await self.utils.fetch_user_config(target_id)
            profile = await client.get_profile()

            if rating_type is None:
                rating_type = (
                    client.DEFAULT_RATING_SYSTEM
                    if not new_rating
                    else RatingType.in_game
                )

            breakdown = await client.get_rating_breakdown(rating_type)

            if rating_type in (RatingType.ongeki, RatingType.ongeki_naive):
                await self._best50_ongeki(ctx, profile, breakdown, user_config)
                return

            current_rating = float(breakdown.rating)
            records = breakdown.frames[RatingFrameType.best].scores
            record_slots = breakdown.frames[RatingFrameType.best].num_scores

            if (new_frame := breakdown.frames.get(RatingFrameType.new)) is not None:
                new_records = new_frame.scores
                new_record_slots = new_frame.num_scores
            else:
                new_records = None
                new_record_slots = 0

            await self._best50_respond(
                ctx,
                profile,
                user_config,
                current_rating,
                records,
                record_slots,
                new_records,
                new_record_slots,
                classic=classic,
            )

    async def _best50_respond(
        self,
        ctx: PenguinContext,
        profile: Profile,
        user_config: UserConfig,
        current_rating: float | None,
        records: list[PersonalBest],
        record_slots: int,
        new_records: list[PersonalBest] | None,
        new_record_slots: int,
        *,
        classic: bool,
    ):
        if classic:
            if new_records is not None:
                view = B30N20View(
                    ctx,
                    records,
                    new_records,
                    synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                )
            else:
                view = B30View(
                    ctx,
                    records,
                    record_slots,
                    show_reachable=False,
                    synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                )

            await view.start()

            return

        uncross_verse = self._random.random() <= 0.1

        if uncross_verse:
            await self.bot.database.user_found_easter_egg(
                ctx.author.id, "chunithm-uncross-verse"
            )

        async with AsyncTemporaryFile() as f:
            await asyncio.to_thread(
                render_b30,
                player_name=profile.username,
                output=f,
                records=records,
                record_slots=record_slots,
                new_records=new_records,
                new_record_slots=new_record_slots,
                current_rating=current_rating,
                user_config=user_config,
                uncross_verse=uncross_verse,
            )

            generation_timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")

            await ctx.respond_or_edit(
                files=[
                    discord.File(
                        f,
                        filename=f"chuni-penguin-b50-{profile.username}-{generation_timestamp}.png",
                    )
                ],
            )

    @flags.command("best50", aliases=["best30", "b30", "b50"])
    @flags.argument("-c", "--classic", action="store_true")
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("-n", "--new-rating", action="store_true")
    @flags.argument(
        "-r",
        "--rating-system",
        choices=["naive", "ingame", "ongeki", "ongeki-naive"],
        default=None,
        required=False,
    )
    @flags.argument("user", nargs="?", default=None)
    @commands.cooldown(15, 600, commands.BucketType.member)
    @logged_prefix_command
    async def best50(
        self,
        ctx: PenguinContext,
        *,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
        rating_system: Literal["naive", "ingame", "ongeki", "ongeki-naive"]
        | None = None,
        user: str | None = None,
    ):
        """View top 50 scores of you or another player.

        **Parameters**:
        `user`: The user to get scores for. Alternatively, a CHUNITHM International friend code is also accepted.
        `-c, --classic`: View your scores with Discord embeds instead of generating an image.
        `-k, --kamaitachi`: Get the best 50 scores from Kamaitachi, if the user has that linked.
        `-n, --new-rating`: Calculates best30 + new20 instead of best50.
        `-r, --rating-system`: Choose from: `ingame` (best30 + new20), `naive` (best50), `ongeki` (best50 + new10 + "platinum50" with ongeki formula), `ongeki-naive` (best60 + "platinum50" with ongeki formula). `-r ingame` is functionally equivalent to `-n`.
        """

        if not classic and not ctx.bot_permissions.attach_files:
            raise commands.BotMissingPermissions(["attach_files"])

        kwargs = {
            "classic": classic,
            "kamaitachi": kamaitachi,
            "new_rating": new_rating,
            "rating_system": rating_system,
        }

        if user is not None:
            try:
                discord_user = await MemberOrUserConverter().convert(ctx, user)

                await self._best50_inner(ctx, discord_user, **kwargs)
            except commands.UserNotFound:
                if kamaitachi or not user.isdigit():
                    raise

                await self._best50_from_friend_code(
                    ctx, user, classic=classic, rating_system=rating_system
                )
        else:
            await self._best50_inner(ctx, None, **kwargs)

    @app_commands.command(name="best50", description="View top plays")
    @app_commands.checks.cooldown(15, 600, key=lambda i: i.user.id)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to get best50 for",
        friend_code="The friend code to get best50 for",
        classic="View your best 50 scores using Discord embeds instead of an image",
        kamaitachi="Get your best 50 from Kamaitachi if linked",
        new_rating="(Kamaitachi) Calculates best30+new20 instead of best50",
        rating_system="The rating system to view the best50 for",
    )
    @app_commands.rename(
        friend_code="friend-code",
        new_rating="new-rating",
        rating_system="rating-system",
    )
    @app_commands.choices(
        rating_system=[
            app_commands.Choice(name="In-game (Best 30 + New 20)", value="ingame"),
            app_commands.Choice(name="Naive (Best 50)", value="naive"),
            app_commands.Choice(
                name='O.N.G.E.K.I. (Best 50 + New 10 + "Platinum 50")', value="ongeki"
            ),
            app_commands.Choice(
                name='O.N.G.E.K.I. Naive (Best 60 + "Platinum 50")',
                value="ongeki-naive",
            ),
        ]
    )
    @logged_app_command
    async def best50_slash(
        self,
        interaction: Interaction["ChuniBot"],
        user: discord.User | discord.Member | None = None,
        *,
        friend_code: str | None = None,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
        rating_system: Literal["naive", "ingame", "ongeki", "ongeki-naive"]
        | None = None,
    ):
        if friend_code is not None and user is not None:
            msg = "Cannot specify both a user and a friend code."
            raise commands.BadArgument(msg)

        if friend_code is not None and not friend_code.isdigit():
            msg = "Invalid friend code."
            raise commands.BadArgument(msg)

        ctx = await PenguinContext.from_interaction(interaction)

        if friend_code is not None:
            await self._best50_from_friend_code(
                ctx,
                friend_code,
                classic=classic,
                rating_system=rating_system,
            )
        else:
            await self._best50_inner(
                ctx,
                user,
                classic=classic,
                kamaitachi=kamaitachi,
                new_rating=new_rating,
                rating_system=rating_system,
            )

    @app_commands.command(name="top", description="View your best scores for a level.")
    @app_commands.describe(
        level="Level (from 1 to 15+) to search for.",
        difficulty="Difficulty to search for.",
        genre="Genre to search for.",
        rank="Rank to search for.",
        sort="Sort records by a criteria (default rating).",
        sort_order="Specify the order to sort records by.",
        version="Version to search for.",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account",
    )
    @app_commands.choices(
        level=[
            *[app_commands.Choice(name=str(i), value=str(i)) for i in range(1, 7)],
            *itertools.chain.from_iterable(
                [
                    (
                        app_commands.Choice(name=f"{i}", value=f"{i}"),
                        app_commands.Choice(name=f"{i}+", value=f"{i}+"),
                    )
                    for i in range(7, 16)
                ]
            ),
        ],
        difficulty=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Difficulty.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        genre=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Genre.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        rank=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Rank.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        version=[
            app_commands.Choice(name=x, value=x) for x in ChunithmVersion.__args__
        ],
    )
    @logged_app_command
    async def top_slash(
        self,
        interaction: "discord.Interaction[ChuniBot]",
        *,
        user: Optional[discord.User | discord.Member] = None,
        level: Optional[str] = None,
        difficulty: Optional[Difficulty] = None,
        genre: Optional[Genre] = None,
        rank: Optional[Rank] = None,
        sort: Literal[
            "rating",
            "score",
            "overpower",
            "overpower %",
            "note lamp",
            "clear lamp",
            "life",
        ] = "rating",
        sort_order: Literal["ascending", "descending"] = "descending",
        version: str | None = None,
        kamaitachi: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)
        target_user_id = interaction.user.id if user is None else user.id

        async with ctx.bot.chunithm_networks.network(
            ctx, target_user_id, kamaitachi=kamaitachi
        ) as client:
            # legacy behavior
            if (
                isinstance(client, ChunithmNetAdapter)
                and level is None
                and difficulty is None
                and genre is None
                and rank is None
                and version is None
            ):
                await self._best50_inner(ctx, user)
                return

            await interaction.response.defer()

            try:
                records = await client.get_personal_bests(
                    level=level,
                    difficulty=difficulty,
                    genre=genre,
                    rank=rank,
                    version=version,  # pyright: ignore[reportArgumentType]
                )
            except ValueError as e:
                raise commands.BadArgument(str(e)) from None

            if len(records) == 0:
                await interaction.followup.send("No scores found.")
                return

        if sort == "rating":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.rating,
                    x.score,
                    x.overpower,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "score":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.score,
                    x.rating,
                    x.overpower,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "overpower":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.overpower,
                    x.rating,
                    x.score,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "overpower %":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    (
                        Decimal(0)
                        if x.chart.max_overpower is None
                        else ((x.overpower or Decimal(0)) / x.chart.max_overpower)
                    ),
                    x.overpower,
                    x.rating,
                    x.score,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "note lamp":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.combo_lamp.value,
                    x.rating,
                    x.score,
                    x.overpower,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "clear lamp":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.clear_lamp.value,
                    x.rating,
                    x.score,
                    x.overpower,
                    x.combo_lamp.value,
                ),
            )
        elif sort == "life":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    Reversor(
                        (x.judgements.justice + x.judgements.attack + x.judgements.miss)
                        if x.judgements is not None and x.clear_lamp != ClearLamp.failed
                        else math.inf
                    ),
                    x.rating,
                    x.score,
                    x.overpower,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )

        view = B30View(
            ctx,
            records,
            show_average=False,
            show_reachable=False,
            show_lamps=True,
            synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
        )
        await view.start()

        return

    @flags.command("top", aliases=["bottom"])
    @flags.argument("-d", "--difficulty", required=False, type=DifficultyConverter)
    @flags.argument("-g", "--genre", required=False, type=GenreConverter)
    @flags.argument("-r", "--rank", required=False, type=RankConverter)
    @flags.argument(
        "-s",
        "--sort",
        choices=[
            key + order
            for key in (
                "score",
                "rating",
                "op",
                "op_percent",
                "overpower",
                "overpower_percent",
                "note_lamp",
                "notelamp",
                "clear_lamp",
                "clearlamp",
                "hp",
                "life",
            )
            for order in ("", "-", "+")
        ],
        nargs="+",
        required=False,
    )
    @flags.argument("-v", "--version", required=False, type=VersionConverter)
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument(
        "user", nargs=flags.OPTIONAL_INVISIBLE, default=None, type=MemberOrUserConverter
    )
    @flags.argument("level", nargs="?", default=None)
    @logged_prefix_command
    async def top(
        self,
        ctx: PenguinContext,
        *,
        difficulty: Difficulty | None = None,
        genre: Genre | None = None,
        rank: Rank | None = None,
        sort: list[str] | None = None,
        version: ChunithmVersion | None = None,
        kamaitachi: bool = False,
        user: discord.User | discord.Member | None = None,
        level: str | None = None,
    ):
        """
        **View your best scores for a level.**

        **Parameters:**
        `user`: Discord username of the player. Yourself, if not provided.
        `level`: Level (from 1 to 15+) to search for.
        `-d`: Difficulty to search for. Must be one of `BASIC`, `ADVANCED`, `EXPERT`, `MASTER`, `ULTIMA`, or `WE` if specified.
        `-g`: Genre to search for.
        `-r`: Rank to search for.
        `-s`: Choose a metric to sort scores by. You can specify multiple metrics, e.g. `-s score clear_lamp`. You can optionally add `+` or `-` after a metric to sort in ascending or descending order, e.g. `score+`. The default is to sort by rating, then score, then overpower, then note lamp, then clear lamp, in descending order. Supported options are:
        - `score`: Sort by score.
        - `rating`: Sort by calculated play rating. Might not work if there are unknown songs.
        - `overpower`: Sort by calculated raw overpower value.
        - `overpower_percent`: Sort by calculated overpower percentage.
        - `note_lamp`: Sort by note lamp (also known as combo lamp, e.g. FULL COMBO/ALL JUSTICE).
        - `clear_lamp`: Sort by clear lamp (FAILED, CLEAR, HARD, BRAVE, ABSOLUTE, CATASTROPHY).
        - `life`: Sort by total number of JUSTICE/ATTACK/MISS, if data is available.
        `-k`: Get scores from Kamaitachi, if the target user has a linked account.

        On CHUNITHM-NET, at least level or difficulty must be set.

        If multiple parameters are set, they will be applied in order of level, difficulty, genre, rank.

        **Examples:**
        `c>top 14+`: View your best scores for level 14+
        `c>top -d mas`: View your best scores for MASTER difficulty
        `c>top -g original -d ultima`: View your best scores for ULTIMA difficulty in the ORIGINAL folder
        `c>top @player -r sss -d mas`: View @player's best scores for SSS rank on MASTER difficulty.
        """

        target_user_id = ctx.author.id if user is None else user.id

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, target_user_id, kamaitachi=kamaitachi
            ) as client,
        ):
            if (
                isinstance(client, ChunithmNetAdapter)
                and level is None
                and difficulty is None
                and genre is None
                and rank is None
                and version is None
            ):
                if not ctx.bot_permissions.attach_files:
                    raise commands.BotMissingPermissions(["attach_files"])

                if ctx.invoked_with == "bottom":
                    raise commands.CommandNotFound

                await self._best50_inner(ctx, user)
                return

            level_folder: str | None = None
            internal_level: float | None = None

            if level is not None:
                level_data = await LevelConverter().convert(ctx, level)
                level_folder = level_data.level
                internal_level = level_data.const

            try:
                records = await client.get_personal_bests(
                    level=level_folder,
                    difficulty=difficulty,
                    genre=genre,
                    rank=rank,
                    version=version,
                )
            except ValueError as e:
                raise commands.BadArgument(str(e)) from None

            if internal_level is not None:
                records = [
                    r for r in records if r.chart.internal_level == internal_level
                ]

            if len(records) == 0:
                await ctx.reply("No scores found.", mention_author=False)
                return

            sort_fns: list[Callable[[Score], Any]] = []

            if sort is not None:
                for item in sort:
                    sort_fn: Callable[[Score], Any] = lambda score: None

                    if item.startswith("score"):
                        sort_fn = lambda score: score.score
                    elif item.startswith("rating"):
                        sort_fn = lambda score: score.rating or Decimal(0)
                    elif item.startswith(("op_percent", "overpower_percent")):
                        sort_fn = lambda score: (
                            score.overpower / score.chart.max_overpower * 100
                            if score.overpower is not None
                            and score.chart.max_overpower is not None
                            else Decimal(0)
                        )
                    elif item.startswith(("op", "overpower")):
                        sort_fn = lambda score: score.overpower or Decimal(0)
                    elif item.startswith(("note_lamp", "notelamp")):
                        sort_fn = lambda score: score.combo_lamp.value
                    elif item.startswith(("clear_lamp", "clearlamp")):
                        sort_fn = lambda score: score.clear_lamp.value
                    elif item.startswith(("hp", "life")):
                        sort_fn = (
                            lambda score: (
                                score.judgements.justice
                                + score.judgements.attack
                                + score.judgements.miss
                            )
                            if (
                                score.judgements is not None
                                and score.clear_lamp != ClearLamp.failed
                            )
                            else math.inf
                        )

                    # other metrics are default descending, but hp/life is default
                    # ascending, since lower number of mistakes is better
                    apply_reversor = True

                    if item.startswith(("hp", "life")):
                        apply_reversor = item.endswith("-")
                    else:
                        apply_reversor = not item.endswith("+")

                    if apply_reversor:
                        sort_fns.append(
                            lambda score, sort_fn=sort_fn: Reversor(sort_fn(score))
                        )
                    else:
                        sort_fns.append(sort_fn)

            # fallback metrics
            sort_fns.extend(
                [
                    lambda score: Reversor(score.rating),
                    lambda score: Reversor(score.score),
                    lambda score: (
                        score.judgements.justice
                        + score.judgements.attack
                        + score.judgements.miss
                    )
                    if (
                        score.judgements is not None
                        and score.clear_lamp != ClearLamp.failed
                    )
                    else math.inf,
                    lambda score: Reversor(score.overpower),
                    lambda score: Reversor(score.combo_lamp.value),
                    lambda score: Reversor(score.clear_lamp.value),
                ]
            )

            records.sort(
                key=lambda score: tuple([sort_fn(score) for sort_fn in sort_fns]),
                reverse=ctx.invoked_with == "bottom",
            )

        view = B30View(
            ctx,
            records,
            show_average=False,
            show_reachable=False,
            show_lamps=True,
            synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
        )
        await view.start()

    @flags.command("leaderboard", aliases=["lb"])
    @flags.argument("-c", "--chunithm-net", action="store_true")
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("difficulty", type=DifficultyConverter)
    @flags.argument("query", nargs="+")
    @logged_prefix_command
    async def leaderboard(
        self,
        ctx: PenguinContext,
        *,
        difficulty: Difficulty,
        query: list[str],
        chunithm_net: bool = False,
        kamaitachi: bool = False,
    ):
        """View the leaderboard for a specific song and difficulty.

        **Parameters**:
        `difificulty`: Chart difficulty to view the leaderboard for (BAS/ADV/EXP/MAS/ULT).
        `query`: Song title to search for. You don't have to be exact; try things out!
        `-c`, `--chunithm-net`: View the CHUNITHM-NET International leaderboard for the song.
        `-k`, `--kamaitachi`: View the Kamaitachi leaderboard for the song.
        """

        query_str = await AliasNameConverter(lower=True).convert(ctx, " ".join(query))

        if chunithm_net and kamaitachi:
            msg = "You can only select either CHUNITHM-NET International or Kamaitachi."
            raise commands.BadArgument(msg)

        if (
            not chunithm_net and not kamaitachi
        ):  # determine the network based on the user
            try:
                async with ctx.bot.chunithm_networks.network(ctx) as client:
                    kamaitachi = isinstance(client, KamaitachiAdapter)
            except commands.CommandError:
                kamaitachi = False

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.bot_network(kamaitachi=kamaitachi) as client,
        ):
            chart = await ctx.find_chart(
                difficulty, query_str, "Select a chart to see leaderboard for:"
            )

            if chart is None:
                return

            if isinstance(client, ChunithmNetAdapter):
                chart.song.raise_if_not_available()

            try:
                leaderboard = await client.get_chart_leaderboard(
                    chart.song.id, difficulty
                )
            except (SongNotFound, ChartNotFound):
                msg = f"The song **{escape_markdown(chart.song.title)}** is not available on {client.NAME}."
                raise commands.CommandError(msg) from None

        view = LeaderboardView(
            ctx,
            leaderboard,
            chart.song,
            difficulty,
            chart,
            synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
            network=client.NAME,
        )

        if ctx.response is not None:
            await view.start_from(ctx.response, content="")
        else:
            await view.start()

    @app_commands.command(
        name="leaderboard", description="View the leaderboard for the given chart."
    )
    @app_commands.rename(chunithm_net="chunithm-net")
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Difficulty.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
    )
    @app_commands.describe(
        difficulty="Chart difficulty to view the leaderboard for.",
        query="Song title to search for. You don't have to be exact; try things out!",
        kamaitachi="View the Kamaitachi leaderboard for the song.",
        chunithm_net="View the CHUNITHM-NET International leaderboard for the song.",
    )
    @app_commands.autocomplete(query=song_title_autocomplete)
    @logged_app_command
    async def leaderboard_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        difficulty: Difficulty,
        query: app_commands.Transform[str, AliasNameTransformer(lower=True)],
        *,
        kamaitachi: bool = False,
        chunithm_net: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

        await self.leaderboard(
            ctx,
            difficulty=difficulty,
            query=query.split(" "),
            kamaitachi=kamaitachi,
            chunithm_net=chunithm_net,
        )

    @flags.command("statistics", aliases=["stats", "folder", "progress"])
    @flags.argument("-d", "--difficulty", required=False)
    @flags.argument("-g", "--genre", required=False, type=GenreConverter)
    @flags.argument("-v", "--version", required=False, type=VersionConverter)
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("-o", "--omnimix", action="store_true")
    @flags.argument(
        "user", nargs=flags.OPTIONAL_INVISIBLE, default=None, type=MemberOrUserConverter
    )
    @flags.argument("level", nargs="?", default=None, type=LevelRangeConverter)
    @logged_prefix_command
    async def statistics(
        self,
        ctx: PenguinContext,
        *,
        user: discord.User | discord.Member | None = None,
        level: Level | LevelRange | None = None,
        difficulty: str | None = None,
        genre: Genre | None = None,
        version: ChunithmVersion | None = None,
        kamaitachi: bool = False,
        omnimix: bool = False,
    ):
        """View aggregated statistics on a set of charts.

        If only a version is specified, also shows progress towards achieving SPIRIT/TRIBUTE/LEGEND titles.

        **Parameters**:
        `user`: Discord username of the player. Yourself, if not provided.
        `level`: Level (from 1 to 15+) to search for. Can also be a level range (e.g. 14.3-14.5).
        `-d`: Difficulty to search for. Must be one of `BASIC`, `ADVANCED`, `EXPERT`, `MASTER`, `ULTIMA`, or `WE` if specified.
        `-g`: Genre to search for.
        `-v`: Version to search for.
        `-k`: Get scores from Kamaitachi, if the target user has a linked account.
        `-o`: Count removed songs towards statistics and the final count.
        """

        conv_diff: Difficulty | Literal["MASTER+ULTIMA"] | None = None

        if difficulty is not None:
            if difficulty.lower() in (
                "master+ultima",
                "mas+ult",
                "mst+ult",
                "masult",
                "mstult",
            ):
                conv_diff = "MASTER+ULTIMA"
            else:
                conv_diff = await DifficultyConverter().convert(ctx, difficulty)

        await self._statistics_impl(
            ctx,
            user=user,
            level=level,
            difficulty=conv_diff,
            genre=genre,
            version=version,
            kamaitachi=kamaitachi,
            omnimix=omnimix,
        )

    @app_commands.command(
        name="statistics", description="View aggregated statistics on a set of charts."
    )
    @app_commands.describe(
        user="The player. Yourself, if not provided.",
        level="Level (from 1 to 15+) to search for. Can also be a level range (e.g. 14.3-14.5).",
        difficulty="Difficulty to search for.",
        genre="Genre to search for.",
        version="Version to search for.",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account.",
        omnimix="Count removed songs towards statistics and the final count.",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name=str(x), value=str(x))
            for x in Difficulty.__members__.values()
        ]
        + [app_commands.Choice(name="MASTER+ULTIMA", value="MASTER+ULTIMA")],  # type: ignore[reportGeneralTypeIssues]
        genre=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Genre.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        version=[
            app_commands.Choice(name=x, value=x) for x in ChunithmVersion.__args__
        ],
    )
    async def statistics_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        *,
        user: discord.User | discord.Member | None = None,
        level: str | None = None,
        difficulty: str | None = None,
        genre: Genre | None = None,
        version: ChunithmVersion | None = None,
        kamaitachi: bool = False,
        omnimix: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)
        converted_level = (
            await LevelRangeConverter().convert(ctx, level)
            if level is not None
            else None
        )

        await self._statistics_impl(
            await PenguinContext.from_interaction(interaction),
            user=user,
            level=converted_level,
            difficulty=(
                await DifficultyConverter().convert(ctx, difficulty)
                if difficulty is not None and difficulty != "MASTER+ULTIMA"
                else difficulty
            ),
            genre=genre,
            version=version,
            kamaitachi=kamaitachi,
            omnimix=omnimix,
        )

    async def _statistics_impl(
        self,
        ctx: PenguinContext,
        *,
        user: discord.User | discord.Member | None = None,
        level: Level | LevelRange | None = None,
        difficulty: Difficulty | Literal["MASTER+ULTIMA"] | None = None,
        genre: Genre | None = None,
        version: str | None = None,
        kamaitachi: bool = False,
        omnimix: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        async with ctx.typing():
            try:
                async with self.bot.chunithm_networks.network(
                    ctx, target_id, kamaitachi=kamaitachi
                ) as client:
                    profile = await client.get_minimal_profile()
                    username = profile.username
                    client_name = client.NAME
            except (NetworkError, commands.CommandError):
                username = ctx.author.display_name
                client_name = (
                    KamaitachiAdapter.NAME if kamaitachi else ChunithmNetAdapter.NAME
                )

            async with self.bot.begin_db_read() as session:
                pb_query = (
                    select(DBPersonalBest)
                    .where(
                        (DBPersonalBest.discord_id == target_id)
                        & (DBPersonalBest.network == client_name)
                    )
                    .join(Song, DBPersonalBest.song_id == Song.id)
                    .join(
                        Chart,
                        (DBPersonalBest.song_id == Chart.song_id)
                        & (DBPersonalBest.difficulty == Chart.difficulty),
                    )
                    .order_by(
                        DBPersonalBest.score.desc(), Chart.const.desc(), Chart.id.desc()
                    )
                )
                chart_query = (
                    select(Chart)
                    .join(Song, Chart.song_id == Song.id)
                    .where(Chart.song_id.not_in([50, 81]))  # basic and master tutorials
                )

                if client_name == ChunithmNetAdapter.NAME:
                    cond = (Song.available == True) & (Chart.available == True)  # noqa: E712
                    pb_query = pb_query.where(cond)
                    chart_query = chart_query.where(cond)
                elif client_name == KamaitachiAdapter.NAME:
                    if not omnimix:
                        cond = Song.removed == False  # noqa: E712
                        pb_query = pb_query.where(cond)
                        chart_query = chart_query.where(cond)

                    cond = Chart.tachi_chart_id.is_not(None)
                    pb_query = pb_query.where(cond)
                    chart_query = chart_query.where(cond)

                if isinstance(level, LevelRange):
                    if level.min_level is not None:
                        cond = Chart.const >= (
                            level.min_level.const or level.min_level.inferred_const
                        )
                        pb_query = pb_query.where(cond)
                        chart_query = chart_query.where(cond)

                    if level.max_level is not None:
                        cond = Chart.const <= (
                            level.max_level.const or level.max_level.inferred_max_const
                        )
                        pb_query = pb_query.where(cond)
                        chart_query = chart_query.where(cond)
                elif level is not None:
                    if level.const is not None:
                        cond = Chart.const == level.const
                    else:
                        cond = Chart.level == level.level

                    pb_query = pb_query.where(cond)
                    chart_query = chart_query.where(cond)

                if difficulty is not None and isinstance(difficulty, Difficulty):
                    cond = Chart.difficulty == difficulty.short()
                elif difficulty is not None:
                    cond = Chart.difficulty.in_(
                        [Difficulty.master.short(), Difficulty.ultima.short()]
                    )
                else:
                    cond = Chart.difficulty != Difficulty.worlds_end.short()

                pb_query = pb_query.where(cond)
                chart_query = chart_query.where(cond)

                if genre is not None:
                    cond = Song.genre == str(genre)
                    pb_query = pb_query.where(cond)
                    chart_query = chart_query.where(cond)

                if version is not None:
                    cond = Song.version == version
                    pb_query = pb_query.where(cond)
                    chart_query = chart_query.where(cond)

                pbs = (await session.execute(pb_query)).scalars().all()
                charts = (await session.execute(chart_query)).scalars().all()

            chart_count = len(charts)

            if chart_count <= 0:
                await ctx.respond_or_edit("No charts found for the given parameters.")
                return

            pb_count = len(pbs)
            percentage_played = pb_count * 10000 // chart_count / 100
            counts: Counter[Any] = Counter([chart.difficulty for chart in charts])

            for pb in pbs:
                pb_rank = Rank.from_score(pb.score)
                pb_combo_lamp = ComboLamp(pb.combo_lamp)
                pb_clear_lamp = ClearLamp(pb.clear_lamp)

                # Checking for AJ is probably unnecessary since currently 1009900
                # guarantees an AJ... until a chart with 5100+ notes is added
                if pb.score >= 1009900 and pb_combo_lamp == ComboLamp.all_justice:
                    counts["99AJ"] += 1

                for rank in (Rank.s, Rank.sp, Rank.ss, Rank.ssp, Rank.sss, Rank.sssp):
                    if pb_rank.value >= rank.value:
                        counts[rank] += 1

                        if rank.value >= Rank.s.value:
                            counts[f"{pb.difficulty}_{rank}"] += 1

                for combo_lamp in ComboLamp:
                    if combo_lamp == ComboLamp.none:
                        continue

                    if pb_combo_lamp.value >= combo_lamp.value:
                        counts[combo_lamp] += 1

                        if combo_lamp == ComboLamp.all_justice:
                            counts[f"{pb.difficulty}_{combo_lamp}"] += 1

                for clear_lamp in ClearLamp:
                    if clear_lamp == ClearLamp.failed:
                        continue

                    if pb_clear_lamp.value >= clear_lamp.value:
                        counts[clear_lamp] += 1

            embed = discord.Embed(
                color=discord.Color.yellow(),
                title=f"{escape_markdown(username)}'s folder statistics",
                timestamp=max(
                    (pb.last_played_at for pb in pbs if pb.last_played_at is not None),
                    default=None,
                ),
            )
            embed.set_footer(
                text=f"Use `{ctx.clean_prefix}sync` if statistics seem wrong."
            )

            option_parts: list[str] = []
            description_parts: list[str] = []

            if level is not None:
                option_parts.append(f"Level {level}")

            if difficulty is not None:
                option_parts.append(str(difficulty))

            if genre is not None:
                option_parts.append(str(genre))

            if version is not None:
                option_parts.append(version)

            if omnimix:
                option_parts.append("Omnimix")

            description_parts.append(", ".join(option_parts))
            description_parts.append(
                f"\n▸ **Played**: {bold_if(len(pbs) == chart_count, f'{len(pbs)} / {chart_count} ({percentage_played:.2f}%)')}\n"
            )

            if any(chart.const is not None for chart in charts):
                charts_by_id_difficulty: dict[tuple[int, str], Chart] = {}
                op_by_song: dict[int, Decimal] = {}
                pb_op_by_song: dict[int, Decimal] = {}

                for chart in charts:
                    if chart.const is None:
                        continue

                    charts_by_id_difficulty[(chart.song_id, chart.difficulty)] = chart

                    if chart.const is not None:
                        op_by_song[chart.song_id] = max(
                            op_by_song.get(chart.song_id, Decimal(0)),
                            calculate_overpower_max(chart.const),
                        )

                for pb in pbs:
                    pb_combo_lamp = ComboLamp(pb.combo_lamp)
                    chart = charts_by_id_difficulty.get((pb.song_id, pb.difficulty))

                    if chart is None or chart.const is None:
                        continue

                    pb_op_by_song[chart.song_id] = max(
                        pb_op_by_song.get(chart.song_id, Decimal(0)),
                        (
                            Decimal(pb.overpower) / 1000
                            if pb.overpower is not None
                            else calculate_play_overpower(
                                calculate_overpower_base(pb.score, chart.const),
                                pb_combo_lamp,
                            )
                        ),
                    )

                op = floor_to_ndp(sum(pb_op_by_song.values(), Decimal(0)), 2)
                total_op = floor_to_ndp(sum(op_by_song.values(), Decimal(0)), 2)
                total_played_op = floor_to_ndp(
                    sum(
                        (
                            max_op
                            for song_id, max_op in op_by_song.items()
                            if song_id in pb_op_by_song
                        ),
                        Decimal(0),
                    ),
                    2,
                )
                op_percent = (
                    floor_to_ndp(op * 100 / total_op, 2) if total_op > 0 else Decimal(0)
                )
                op_played_percent = (
                    floor_to_ndp(op * 100 / total_played_op, 2)
                    if total_played_op > 0
                    else Decimal(0)
                )

                # TODO: update when new filters are added; embed colors are only calculated
                # by possession rules on the full view
                if (
                    level is None
                    and (difficulty is None or difficulty == "MASTER+ULTIMA")
                    and genre is None
                    and version is None
                ):
                    total_mas_ult = counts["MAS"] + counts["ULT"]

                    # Don't bother with the rating check because if you S every MAS/ULT
                    # you're going to end up above 16 rating anyways.
                    if op_percent >= Decimal("99.5") and (
                        counts[f"MAS_{Rank.sss}"] + counts[f"ULT_{Rank.sss}"]
                        == total_mas_ult
                    ):
                        embed.color = Possession.rainbow.color
                    elif op_percent >= 99 and (
                        counts[f"MAS_{Rank.ss}"] + counts[f"ULT_{Rank.ss}"]
                        == total_mas_ult
                    ):
                        embed.color = Possession.platinum.color
                    elif op_percent >= Decimal("97.5") and (
                        counts[f"MAS_{Rank.sp}"] + counts[f"ULT_{Rank.sp}"]
                        == total_mas_ult
                    ):
                        embed.color = Possession.gold.color
                    elif (
                        counts[f"MAS_{Rank.s}"] + counts[f"ULT_{Rank.s}"]
                        == total_mas_ult
                    ):
                        embed.color = Possession.silver.color
                    else:
                        embed.color = Possession.none.color

                description_parts.append(
                    f"▸ **OVER POWER**: {bold_if(op == total_op, f'{op} / {total_op} ({op_percent:.2f}%)')}\n"
                    f"▸ **OVER POWER (played)**: {bold_if(op == total_played_op, f'{op} / {total_played_op} ({op_played_percent:.2f}%)')}\n"
                )

            description_parts.append(
                f"▸ **Average score (played)**: {int(statistics.fmean(pb.score for pb in pbs)) if len(pbs) > 0 else 0}\n"
                f"▸ **Average score (all)**: {int(sum(pb.score for pb in pbs) / chart_count)}\n"
            )

            rank_parts = [
                f"{config.icons.rank_icon(rank) if rank != '99AJ' else rank} {bold_if(counts[rank] == chart_count, counts[rank])}"
                for rank in (
                    "99AJ",
                    Rank.sssp,
                    Rank.sss,
                    Rank.ssp,
                    Rank.ss,
                    Rank.sp,
                    Rank.s,
                )
            ]
            description_parts.append(f"▸ **Ranks**: {' / '.join(rank_parts)}")

            combo_lamp_parts = [
                f"{combo_lamp.short()} {bold_if(counts[combo_lamp] == chart_count, counts[combo_lamp])}"
                for combo_lamp in ComboLamp
                if combo_lamp != ComboLamp.none
            ]
            combo_lamp_parts.reverse()
            description_parts.append(
                f"▸ **Combo lamps**: {' / '.join(combo_lamp_parts)}"
            )

            clear_lamp_parts = [
                f"{clear_lamp.short()} {bold_if(counts[clear_lamp] == chart_count, counts[clear_lamp])}"
                for clear_lamp in ClearLamp
                if clear_lamp != ClearLamp.failed
            ]
            clear_lamp_parts.reverse()
            description_parts.append(
                f"▸ **Clear lamps**: {' / '.join(clear_lamp_parts)}\n"
            )

            # TODO: update this if new filters are added; only the full version view should
            # show title completion
            if (
                version is not None
                and level is None
                and difficulty is None
                and genre is None
            ):
                description_parts.append("▸ **Title completion**:")
                description_parts.append(
                    "`Total  ` ▸ "
                    f"{Difficulty.basic.emoji()} {bold(counts[Difficulty.basic.short()])}"
                    f" / {Difficulty.advanced.emoji()} {bold(counts[Difficulty.advanced.short()])}"
                    f" / {Difficulty.expert.emoji()} {bold(counts[Difficulty.expert.short()])}"
                    f" / {Difficulty.master.emoji()} {bold(counts[Difficulty.master.short()])}"
                )
                description_parts.extend(
                    [
                        (
                            f"{name} ▸ "
                            f"{Difficulty.basic.emoji()} {bold_if(counts[f'{Difficulty.basic.short()}_{criteria}'] == counts[Difficulty.basic.short()], counts[f'{Difficulty.basic.short()}_{criteria}'])}"
                            f" / {Difficulty.advanced.emoji()} {bold_if(counts[f'{Difficulty.advanced.short()}_{criteria}'] == counts[Difficulty.advanced.short()], counts[f'{Difficulty.advanced.short()}_{criteria}'])}"
                            f" / {Difficulty.expert.emoji()} {bold_if(counts[f'{Difficulty.expert.short()}_{criteria}'] == counts[Difficulty.expert.short()], counts[f'{Difficulty.expert.short()}_{criteria}'])}"
                            f" / {Difficulty.master.emoji()} {bold_if(counts[f'{Difficulty.master.short()}_{criteria}'] == counts[Difficulty.master.short()], counts[f'{Difficulty.master.short()}_{criteria}'])}"
                        )
                        for name, criteria in [
                            ("`SPIRIT `", Rank.s),
                            ("`TRIBUTE`", Rank.sss),
                            ("`LEGEND `", ComboLamp.all_justice),
                        ]
                    ]
                )

            embed.description = "\n".join(description_parts)
            embeds = [embed]
            featured_scores: list[DBPersonalBest] = []

            if len(pbs) >= 2:
                featured_scores = [pbs[0], pbs[-1]]
            elif len(pbs) > 0:
                featured_scores = [pbs[0]]

            embeds += [
                ScoreCardEmbed(
                    await self.utils.convert_to_network_pb(pb),
                    synthesis_alt_jacket=ctx.user_config.synthesis_alt_jacket,
                )
                for pb in featured_scores
            ]

        await ctx.respond_or_edit(embeds=embeds)

    @flags.command("sync", aliases=["refresh", "update"])
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("user", nargs=flags.OPTIONAL_INVISIBLE, default=None)
    @commands.cooldown(2, 60, commands.BucketType.user)
    async def sync(
        self,
        ctx: PenguinContext,
        *,
        user: str | None = None,
        kamaitachi: bool = False,
    ):
        """Sync scores with the bot.

        It is usually not necessary to use this command, since the bot will automatically track scores as they are fetched from other commands like `c>best50` or `c>recent`.

        Currently scores stored in the bot are only used for `$PREFIXstatistics`. This may change in the future.

        **Parameters**:
        `-k`: Sync the user's Kamaitachi scores.
        `user`: The user to sync scores for. Yourself, if not specified. Alternatively, a CHUNITHM International friend code is also accepted.
        """

        user_or_friend_code: discord.User | discord.Member | str | None = None

        if user is not None:
            try:
                user_or_friend_code = await MemberOrUserConverter().convert(ctx, user)
            except commands.UserNotFound:
                if kamaitachi or not user.isdigit():
                    raise

                user_or_friend_code = user

        await self._sync_impl(ctx, user=user_or_friend_code, kamaitachi=kamaitachi)

    @app_commands.command(name="sync", description="Sync scores with the bot.")
    @app_commands.describe(
        user="The user to sync scores for.",
        friend_code="The friend code to sync scores for.",
        kamaitachi="Sync the user's Kamaitachi scores.",
    )
    @app_commands.rename(friend_code="friend-code")
    @app_commands.checks.cooldown(2, 60)
    async def sync_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        *,
        user: discord.User | discord.Member | None = None,
        friend_code: str | None = None,
        kamaitachi: bool = False,
    ):
        if friend_code is not None and user is not None:
            msg = "Cannot specify both a user and a friend code."
            raise commands.BadArgument(msg)

        if friend_code is not None and not friend_code.isdigit():
            msg = "Invalid friend code."
            raise commands.BadArgument(msg)

        await self._sync_impl(
            await PenguinContext.from_interaction(interaction),
            user=friend_code or user,
            kamaitachi=kamaitachi,
        )

    async def _sync_impl(
        self,
        ctx: PenguinContext,
        *,
        user: discord.User | discord.Member | str | None = None,
        kamaitachi: bool = False,
    ):
        if isinstance(user, str):
            async with ctx.typing():
                (
                    profile,
                    _,
                ) = await ctx.bot.chunithm_networks.fetch_chunithm_net_from_friend_code(
                    ctx, user
                )

            await ctx.respond_or_edit(
                f"Successfully synced CHUNITHM International scores for {escape_markdown(profile.username)}."
            )
            return

        target_id = user.id if user is not None else ctx.author.id
        cookie = await self.bot.database.cookies.get_by_discord_id(target_id)

        if (
            user is None
            and not kamaitachi
            and (
                cookie is None
                or (not cookie.cookie and cookie.kamaitachi_token is None)
            )
        ):
            view = FriendCodeOfferView(
                ctx, cookie.friend_code if cookie is not None else None
            )
            await view.start()
            return

        async with (
            ctx.typing(),
            self.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            profile = await client.get_minimal_profile()

            await ctx.respond_or_edit(f"Fetching recent scores from {client.NAME}...")

            recents = await client.get_recent_scores()

            if client.SUPPORTS_DETAILED_RECENT_SCORE:
                for i, recent in enumerate(recents):
                    if (i + 1) % 10 == 0 or (i + 1) == len(recents):
                        await ctx.respond_or_edit(
                            f"Fetching recent scores from {client.NAME}... {i + 1}/{len(recents)}"
                        )

                    # Side effect: also processes scores
                    _ = await client.get_detailed_recent_score(recent)

            await ctx.respond_or_edit(f"Fetching personal bests from {client.NAME}...")

            # Side effect: fetches PBs and puts them into the database
            _ = await client.get_all_personal_bests()

        await ctx.respond_or_edit(
            f"Successfully synced {client.NAME} scores for {escape_markdown(profile.username)}."
        )

    @commands.group("ranking", invoke_without_command=True)
    async def ranking_prefix(self, ctx: PenguinContext):
        """
        View rankings for teams, rating, scores and currency.
        """

        await ctx.send_help(ctx.command)

    @ranking_prefix.command("team")
    async def ranking_team_prefix(self, ctx: PenguinContext, month: str | None = None):
        """
        View team rankings.

        Only available for CHUNITHM International.

        **Parameters**
        `month`: The month to view team rankings for (e.g. 2026/04). If omitted, default to most recent team ranking.
        """

        await self._ranking_team_impl(ctx, month)

    @ranking_prefix.command("rating", cls=flags.FlagCommand)
    @flags.argument("-c", "--chunithm-net", action="store_true")
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("type", nargs="?", default="global", choices=["friend", "global"])
    async def ranking_rating_prefix(
        self,
        ctx: PenguinContext,
        *,
        chunithm_net: bool = False,
        kamaitachi: bool = False,
        type: Literal["friend", "global"] = "global",
    ):
        """
        View player rankings on rating.

        **Paramters**
        `-c`: View CHUNITHM International rankings.
        `-k`: View Kamaitachi rankings.
        `type`: The ranking type to view. If not specified, show global rankings. Friend rankings are only supported for CHUNITHM International.
        """

        await self._ranking_rating_impl(
            ctx, type, chunithm_net=chunithm_net, kamaitachi=kamaitachi
        )

    @ranking_prefix.command("score")
    async def ranking_score_prefix(
        self,
        ctx: PenguinContext,
        difficulty: Annotated[Difficulty | None, RankingDifficultyConverter] = None,
        type: Literal["friend", "global"] = "global",
    ):
        """
        View player rankings on total highscore.

        Only available for CHUNITHM International.

        **Paramters**:
        `difficulty`: The difficulty to view. If not specified or `all`, show total highscore across all difficulties.
        `type`: The ranking type to view. If not specified, show global rankings. Friend rankings are only supported for CHUNITHM International.
        """

        await self._ranking_score_impl(ctx, type, difficulty)

    @ranking_prefix.command("currency", aliases=["memory", "point"])
    async def ranking_currency_prefix(
        self, ctx: PenguinContext, type: Literal["friend", "global"] = "global"
    ):
        """
        View player rankings on total currency obtained.

        Only available for CHUNITHM International.

        **Paramters**:
        `type`: The ranking type to view. If not specified, show global rankings. Friend rankings are only supported for CHUNITHM International.
        """

        await self._ranking_currency_impl(ctx, type)

    ranking_slash = app_commands.Group(
        name="ranking",
        description="View rankings for teams, rating, scores and currency.",
    )

    @ranking_slash.command(name="team", description="View team rankings.")
    @app_commands.describe(month="The month to view team rankings for (e.g. 2026/04).")
    async def ranking_team_slash(
        self, interaction: discord.Interaction["ChuniBot"], month: str | None = None
    ):
        await self._ranking_team_impl(
            await PenguinContext.from_interaction(interaction), month
        )

    @ranking_slash.command(name="rating", description="View player rankings on rating.")
    @app_commands.rename(chunithm_net="chunithm-net")
    @app_commands.describe(
        type="The ranking type to view. If not specified, show global rankings.",
        chunithm_net="View CHUNITHM International rankings.",
        kamaitachi="View Kamaitachi rankings.",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Global", value="global"),
            app_commands.Choice(name="Friend", value="friend"),
        ]
    )
    async def ranking_rating_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        type: Literal["friend", "global"] = "global",
        *,
        chunithm_net: bool = False,
        kamaitachi: bool = False,
    ):
        await self._ranking_rating_impl(
            await PenguinContext.from_interaction(interaction),
            type,
            chunithm_net=chunithm_net,
            kamaitachi=kamaitachi,
        )

    @ranking_slash.command(
        name="score", description="View player rankings on total highscore."
    )
    @app_commands.describe(
        difficulty="The difficulty to view. If not specified, show total highscore across all difficulties.",
        type="The ranking type to view. If not specified, show global rankings.",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name=str(x), value=x.value)
            for x in Difficulty.__members__.values()
        ],  # type: ignore[reportGeneralTypeIssues]
        type=[
            app_commands.Choice(name="Global", value="global"),
            app_commands.Choice(name="Friend", value="friend"),
        ],
    )
    async def ranking_score_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        difficulty: Difficulty | None = None,
        type: Literal["friend", "global"] = "global",
    ):
        await self._ranking_score_impl(
            await PenguinContext.from_interaction(interaction), type, difficulty
        )

    @ranking_slash.command(
        name="currency", description="View player rankings on total currency obtained."
    )
    @app_commands.describe(
        type="The ranking type to view. If not specified, show global rankings.",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Global", value="global"),
            app_commands.Choice(name="Friend", value="friend"),
        ]
    )
    async def ranking_currency_slash(
        self,
        interaction: discord.Interaction["ChuniBot"],
        type: Literal["friend", "global"] = "global",
    ):
        await self._ranking_currency_impl(
            await PenguinContext.from_interaction(interaction), type
        )

    async def _ranking_team_impl(self, ctx: PenguinContext, month: str | None = None):
        if month is not None:
            try:
                # Deliberately naive datetime since year/months are usually
                # not subject to timezone nonsense, and networks will have different
                # timezones
                dt = datetime.strptime(  # noqa: DTZ007
                    month.replace("/", "-").replace(".", "-"), "%Y-%m"
                )
            except ValueError:
                msg = f'Invalid month "{escape_markdown(month)}."'
                raise commands.BadArgument(msg) from None

            if dt.month > datetime.now(TOKYO_TZ).month:
                msg = "Cannot specify a month in the future."
                raise commands.BadArgument(msg)
        else:
            dt = None

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.bot_network(kamaitachi=False) as client,
        ):
            try:
                ranking = await client.get_team_ranking(dt)
            except NotImplementedError:
                msg = f"{client.NAME} does not support team rankings."
                raise commands.CommandError(msg) from None

        view = TeamRankingView(
            ctx, client.NAME, discord.Color(client.ACCENT_COLOR), ranking
        )
        await view.start()

    async def _ranking_rating_impl(
        self,
        ctx: PenguinContext,
        type: Literal["friend", "global"],
        *,
        chunithm_net: bool,
        kamaitachi: bool,
    ):
        if chunithm_net and kamaitachi:
            msg = "You can only select either CHUNITHM-NET International or Kamaitachi."
            raise commands.BadArgument(msg)

        ranking_type = RankingType(type)

        # if asking for friend ranking, directly grab user's network
        if ranking_type == RankingType.friend:
            async with (
                ctx.typing(),
                ctx.bot.chunithm_networks.network(
                    ctx, kamaitachi=kamaitachi, chunithm_net=chunithm_net
                ) as client,
            ):
                try:
                    ranking = await client.get_rating_ranking(RankingType(type))
                except NotImplementedError:
                    msg = f"{client.NAME} does not support {type} rankings."
                    raise commands.CommandError(msg) from None
        else:
            if (
                not chunithm_net and not kamaitachi
            ):  # determine the network based on the user
                try:
                    async with ctx.bot.chunithm_networks.network(ctx) as client:
                        kamaitachi = isinstance(client, KamaitachiAdapter)
                except commands.CommandError:
                    kamaitachi = False

            async with (
                ctx.typing(),
                ctx.bot.chunithm_networks.bot_network(kamaitachi=kamaitachi) as client,
            ):
                try:
                    ranking = await client.get_rating_ranking(RankingType(type))
                except NotImplementedError:
                    msg = f"{client.NAME} does not support {type} rankings."
                    raise commands.CommandError(msg) from None

        view = RatingRankingView(
            ctx,
            client.NAME,
            discord.Color(client.ACCENT_COLOR),
            RankingType(type),
            ranking,
        )
        await view.start()

    async def _ranking_score_impl(
        self,
        ctx: PenguinContext,
        type: Literal["friend", "global"],
        difficulty: Difficulty | None,
    ):
        ranking_type = RankingType(type)

        async with (
            ctx.typing(),
            (
                ctx.bot.chunithm_networks.network(ctx, ctx.author.id, chunithm_net=True)
                if ranking_type == RankingType.friend
                else ctx.bot.chunithm_networks.bot_network(kamaitachi=False)
            ) as client,
        ):
            try:
                ranking = await client.get_score_ranking(RankingType(type), difficulty)
            except NotImplementedError:
                msg = f"{client.NAME} does not support {type} score rankings on {difficulty}."
                raise commands.CommandError(msg) from None

        view = ScoreRankingView(
            ctx,
            client.NAME,
            discord.Color(client.ACCENT_COLOR),
            RankingType(type),
            difficulty,
            ranking,
        )
        await view.start()

    async def _ranking_currency_impl(
        self, ctx: PenguinContext, type: Literal["friend", "global"]
    ):
        ranking_type = RankingType(type)

        async with (
            ctx.typing(),
            (
                ctx.bot.chunithm_networks.network(ctx, ctx.author.id, chunithm_net=True)
                if ranking_type == RankingType.friend
                else ctx.bot.chunithm_networks.bot_network(kamaitachi=False)
            ) as client,
        ):
            try:
                ranking = await client.get_currency_ranking(RankingType(type))
            except NotImplementedError:
                msg = f"{client.NAME} does not support {type} currency rankings."
                raise commands.CommandError(msg) from None

        view = CurrencyRankingView(
            ctx,
            client.NAME,
            discord.Color(client.ACCENT_COLOR),
            RankingType(type),
            ranking,
        )
        await view.start()


async def setup(bot: "ChuniBot"):
    await bot.add_cog(RecordsCog(bot))
