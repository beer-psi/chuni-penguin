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
from typing import TYPE_CHECKING, Any, Literal, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chuni_penguin import flags
from chuni_penguin.calculation.overpower import (
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
)
from chuni_penguin.config import config
from chuni_penguin.constants import (
    CACHE_DIR,
    CURRENT_CHUNITHM_VERSION,
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
)
from chuni_penguin.database import Chart, Song, SongJacket
from chuni_penguin.database import PersonalBest as DBPersonalBest
from chuni_penguin.logging import logged_app_command, logged_prefix_command
from chuni_penguin.networks.chunithm_net import (
    INTERNATIONAL_JACKET_BASE,
    JACKET_BASE,
    ChunithmNet,
)
from chuni_penguin.networks.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_SONG_GENRE,
    KEY_SONG_ID,
    KEY_SONG_VERSION,
)
from chuni_penguin.networks.errors import ChartNotFound, SongNotFound
from chuni_penguin.networks.kamaitachi import Kamaitachi
from chuni_penguin.networks.types import (
    ClearLamp,
    ComboLamp,
    Difficulty,
    Genre,
    PersonalBest,
    Rank,
    Score,
)
from chuni_penguin.renderers.b50 import render_b30
from chuni_penguin.ui import (
    B30N20View,
    B30View,
    EmbedPaginationView,
    LeaderboardView,
    RecentRecordsView,
    ScoreCardEmbed,
    SelectToCompareView,
)
from chuni_penguin.utils import floor_to_ndp
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
            if not client.SUPPORTS_RECENT_SCORES:
                msg = f"Network {client.NAME} does not support getting recent scores."
                raise commands.CommandError(msg)

            profile = await client.get_minimal_profile()

            recents = await client.get_recent_scores()
            recents = await self.utils.process_records(target_id, client.NAME, recents)

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
            self.bot.begin_db_session() as session,
            ctx.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
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

            if isinstance(client, ChunithmNet):
                song.raise_if_not_available()

            if isinstance(client, Kamaitachi) and song.genre == "WORLD'S END":
                msg = "Kamaitachi does not support WORLD'S END charts."
                raise commands.CommandError(msg)

            displayed_song = escape_markdown(song.title)

            if song.id >= 8000 and len(song.charts) > 0:
                displayed_song += f" [{escape_markdown(song.charts[0].level)}]"

            if not client.SUPPORTS_PERSONAL_BESTS_ON_SONG:
                msg = f"Network {client.NAME} does not support fetching scores for a specific song."
                raise commands.CommandError(msg)

            profile = await client.get_minimal_profile()

            try:
                records = await client.get_personal_bests_on_song(song.id)
            except (SongNotFound, ChartNotFound):
                msg = (
                    f"The song **{displayed_song}** is not available on {client.NAME}."
                )
                raise commands.CommandError(msg) from None

            if len(records) == 0:
                await ctx.respond_or_edit(
                    f"No records found for {profile.username} on **{displayed_song}**."
                )
                return

            records = await self.utils.process_records(target_id, client.NAME, records)
            records.sort(key=lambda r: r.difficulty.value)

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
                        if record.difficulty == difficulty
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

                messages = [x async for x in ctx.channel.history(limit=50) if check(x)]
            except discord.errors.Forbidden as e:
                msg = "Bot requires the Read Message History permission to fetch recent scores."

                if ctx.interaction is None:
                    msg += f" Alternatively, run `{ctx.clean_prefix}compare` while replying to the score you want to compare."

                raise commands.CheckFailure(msg) from e

            if len(messages) == 0:
                msg = "No recent scores found."
                raise commands.CommandError(msg)

            message = messages[0]

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
                if (isinstance(client, Kamaitachi) and x.genre != "WORLD'S END")
                or (isinstance(client, ChunithmNet) and x.available)
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

            records = await self.utils.process_records(target_id, client.NAME, records)
            records.sort(key=lambda r: r.difficulty.value)

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

    async def _best50_inner(
        self,
        ctx: PenguinContext,
        user: discord.User | discord.Member | None = None,
        *,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id
        records: list[PersonalBest] = []
        record_slots: int = 30
        new_records: list[PersonalBest] | None = []
        new_record_slots: int = 20

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            user_config = await self.utils.fetch_user_config(target_id)
            profile = await client.get_profile()

            # Having client-specific behavior sorta goes against the spirit of having a unified
            # network API, but there's too many stupid quirks with this thing.
            if isinstance(client, ChunithmNet):
                current_rating = profile.rating_systems[0].value

                # in order to get extra lamp information, we get the charts that are in a player's
                # best30/new20 from the music for rating list, but we fetch the player's PBs.
                best30_charts = [
                    (x.extras[KEY_SONG_ID], x.difficulty)
                    for x in await client.get_best30()
                ]
                new20_charts = [
                    (x.extras[KEY_SONG_ID], x.difficulty)
                    for x in await client.get_new20()
                ]

                difficulties = sorted(
                    {x[1] for x in itertools.chain(best30_charts, new20_charts)},
                    key=lambda x: x.value,
                )

                for difficulty in difficulties:
                    difficulty_records = await client.get_personal_bests_by_difficulty(
                        difficulty
                    )
                    await self.bot.database.personal_bests.upsert_personal_bests(
                        target_id, client.NAME, difficulty_records
                    )
                    records.extend(
                        [
                            x
                            for x in difficulty_records
                            if (x.extras[KEY_SONG_ID], x.difficulty) in best30_charts
                        ]
                    )
                    new_records.extend(
                        [
                            x
                            for x in difficulty_records
                            if (x.extras[KEY_SONG_ID], x.difficulty) in new20_charts
                        ]
                    )

                records = await self.utils.process_records(
                    target_id, client.NAME, records
                )
                new_records = await self.utils.process_records(
                    target_id, client.NAME, new_records
                )

                # sort the fetched best30/new20 by their position in the original b30/n20 list
                records.sort(
                    key=lambda x: best30_charts.index(
                        (x.extras[KEY_SONG_ID], x.difficulty)
                    )
                )
                new_records.sort(
                    key=lambda x: new20_charts.index(
                        (x.extras[KEY_SONG_ID], x.difficulty)
                    )
                )

                hidden_songs = await ctx.bot.database.songs.get_hidden_on_chuninet()

                # Sometimes, SEGA likes to hide some scores from appearing in
                # CHUNITHM-NET. This is a workaround. Basically:
                # - Fetch music records of all hidden songs
                # - For each record, check if there are already enough slots in the
                # respective new/old rating list:
                #   - If there are already enough rating slots, and if the hidden score's
                # rating is higher than the last item in the rating list, replace the last item
                # with the hidden record.
                #   - If there are not enough rating slots, just add the song as is.
                #   - Sort the list again.
                for hidden_song in hidden_songs:
                    if hidden_song.version == CURRENT_CHUNITHM_VERSION:
                        chart_list = new20_charts
                        record_list = new_records
                        record_list_slots = new_record_slots
                    else:
                        chart_list = best30_charts
                        record_list = records
                        record_list_slots = record_slots

                    hidden_song_records = await self.utils.process_records(
                        target_id,
                        client.NAME,
                        await client.get_personal_bests_on_song(hidden_song.id),
                    )

                    for hidden_song_record in hidden_song_records:
                        if (
                            hidden_song.id,
                            hidden_song_record.difficulty,
                        ) in chart_list:
                            # chart is actually not hidden
                            continue

                        if len(record_list) >= record_list_slots:
                            # record list is definitely sorted by rating
                            min_rating_record = record_list[-1]

                            if (
                                hidden_song_record.extras[KEY_PLAY_RATING]
                                > min_rating_record.extras[KEY_PLAY_RATING]
                            ):
                                del record_list[-1]
                                chart_list.remove(
                                    (
                                        min_rating_record.extras[KEY_SONG_ID],
                                        min_rating_record.difficulty,
                                    )
                                )

                                chart_list.append(
                                    (hidden_song.id, hidden_song_record.difficulty)
                                )
                                record_list.append(hidden_song_record)
                        else:
                            chart_list.append(
                                (hidden_song.id, hidden_song_record.difficulty)
                            )
                            record_list.append(hidden_song_record)

                        record_list.sort(
                            key=lambda r: r.extras[KEY_PLAY_RATING],
                            reverse=True,
                        )
            elif client.SUPPORTS_BEST30 and client.SUPPORTS_NEW20:
                try:
                    rating_system = next(
                        s for s in profile.rating_systems if s.name == "Rating"
                    )
                    current_rating = rating_system.value
                except StopIteration:
                    current_rating = None

                records = await self.utils.process_records(
                    target_id, client.NAME, await client.get_best30()
                )
                new_records = await self.utils.process_records(
                    target_id, client.NAME, await client.get_new20()
                )
            elif new_rating:
                if not client.SUPPORTS_PERSONAL_BESTS:
                    msg = f"Network {client.NAME} does not support best30/new20, and does not support fetching personal bests."
                    raise commands.CommandError(msg)

                pbs = await self.utils.process_records(
                    target_id, client.NAME, await client.get_personal_bests()
                )
                records = [
                    pb
                    for pb in pbs
                    if pb.extras[KEY_SONG_VERSION] != CURRENT_CHUNITHM_VERSION
                ]
                new_records = [
                    pb
                    for pb in pbs
                    if pb.extras[KEY_SONG_VERSION] == CURRENT_CHUNITHM_VERSION
                ]

                records.sort(
                    key=lambda pb: (
                        pb.extras[KEY_PLAY_RATING],
                        pb.score,
                        pb.extras[KEY_INTERNAL_LEVEL],
                    ),
                    reverse=True,
                )
                new_records.sort(
                    key=lambda pb: (
                        pb.extras[KEY_PLAY_RATING],
                        pb.score,
                        pb.extras[KEY_INTERNAL_LEVEL],
                    ),
                    reverse=True,
                )

                records = records[:record_slots]
                new_records = new_records[:new_record_slots]
                current_rating = float(
                    floor_to_ndp(
                        sum(
                            [
                                r.extras[KEY_PLAY_RATING]
                                for r in itertools.chain(records, new_records)
                            ],
                            start=Decimal(0),
                        )
                        / (record_slots + new_record_slots),
                        2,
                    )
                )
            elif client.SUPPORTS_BEST_RATINGS:
                try:
                    rating_system = next(
                        s for s in profile.rating_systems if s.name == "NaiveRating"
                    )
                    current_rating = rating_system.value
                except StopIteration:
                    current_rating = None

                pbs = await client.get_best_ratings()
                pbs = await self.utils.process_records(target_id, client.NAME, pbs)
                pbs = pbs[:50]

                records = pbs
                record_slots = 50

                new_records = None
                new_record_slots = 0
            else:
                msg = f"Network {client.NAME} does not support any features needed for a best50 breakdown."
                raise commands.CommandError(msg)

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

            b30_image = await asyncio.to_thread(
                render_b30,
                profile.username,
                records=records,
                record_slots=record_slots,
                new_records=new_records,
                new_record_slots=new_record_slots,
                current_rating=current_rating,
                user_config=user_config,
                uncross_verse=uncross_verse,
            )
            generation_timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")

            await ctx.reply(
                file=discord.File(
                    b30_image, filename=f"chuni-penguin-b50-{generation_timestamp}.png"
                ),
                mention_author=False,
            )

    @flags.command("best50", aliases=["best30", "b30", "b50"])
    @flags.argument("-c", "--classic", action="store_true")
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("-n", "--new-rating", action="store_true")
    @flags.argument("user", nargs="?", default=None, type=MemberOrUserConverter)
    @commands.cooldown(15, 600, commands.BucketType.member)
    @logged_prefix_command
    async def best50(
        self,
        ctx: PenguinContext,
        *,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
        user: discord.Member | discord.User | None = None,
    ):
        """View top 50 scores of you or another player.

        **Parameters**:
        `user`: The user to get scores for.
        `-c, --classic`: View your scores with Discord embeds instead of generating
        an image.
        `-k, --kamaitachi`: Get the best 50 scores from Kamaitachi, if the user
        has that linked.
        `-n, --new-rating`: For Kamaitachi, calculates best30 + new20 instead of best50.
        Does nothing for official network.
        """

        if not classic and not ctx.bot_permissions.attach_files:
            raise commands.BotMissingPermissions(["attach_files"])

        await self._best50_inner(
            ctx,
            user,
            classic=classic,
            kamaitachi=kamaitachi,
            new_rating=new_rating,
        )

    @app_commands.command(name="best50", description="View top plays")
    @app_commands.checks.cooldown(15, 600, key=lambda i: i.user.id)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(
        user="The user to get best50 for",
        classic="View your best 50 scores using Discord embeds instead of an image",
        kamaitachi="Get your best 50 from Kamaitachi if linked",
        new_rating="(Kamaitachi) Calculates best30+new20 instead of best50",
    )
    @app_commands.rename(new_rating="new-rating")
    @logged_app_command
    async def best50_slash(
        self,
        interaction: Interaction["ChuniBot"],
        user: discord.User | discord.Member | None = None,
        *,
        classic: bool = False,
        kamaitachi: bool = False,
        new_rating: bool = False,
    ):
        ctx = await PenguinContext.from_interaction(interaction)

        await self._best50_inner(
            ctx,
            user,
            classic=classic,
            kamaitachi=kamaitachi,
            new_rating=new_rating,
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
            if (
                not client.SUPPORTS_PERSONAL_BESTS
                and level is None
                and difficulty is None
                and genre is None
                and rank is None
            ):
                await self._best50_inner(ctx, user)
                return

            await interaction.response.defer()

            if level is not None and client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL:
                records = await client.get_personal_bests_by_level(level)
            elif (
                difficulty is not None and client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY
            ):
                records = await client.get_personal_bests_by_difficulty(difficulty)
            elif client.SUPPORTS_PERSONAL_BESTS:
                records = await client.get_personal_bests()
            else:
                if (
                    client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL
                    and client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY
                ):
                    msg = "At least one of `level` or `difficulty` must be specified."
                    exc = commands.BadArgument
                elif client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL:
                    msg = "Level must be specified."
                    exc = commands.BadArgument
                elif client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY:
                    msg = "Difficulty must be specified."
                    exc = commands.BadArgument
                else:
                    msg = f"Network {client.NAME} does not support fetching personal bests."
                    exc = commands.CommandError

                raise exc(msg)

            if isinstance(client, ChunithmNet):
                # hidden chart shenanigans
                hidden_charts = await ctx.bot.database.charts.get_hidden_on_chuninet(
                    level=level, difficulty=difficulty
                )
                hidden_song_ids = {c.song_id for c in hidden_charts}
                record_charts = {(r.extras[KEY_SONG_ID], r.difficulty) for r in records}

                for song_id in hidden_song_ids:
                    # get the records for the hidden chart's song id
                    hidden_records = await client.get_personal_bests_on_song(song_id)

                    # and insert it into our records, if a record is not already there
                    records.extend(
                        [
                            r
                            for r in hidden_records
                            if (song_id, r.difficulty) not in record_charts
                        ]
                    )

            records = await self.utils.process_records(
                target_user_id, client.NAME, records
            )

            if difficulty is not None:
                records = [r for r in records if r.difficulty == difficulty]
            if rank is not None:
                records = [r for r in records if r.rank == rank]
            if level is not None:
                records = [r for r in records if r.extras[KEY_LEVEL] == level]
            if genre is not None:
                records = [r for r in records if r.extras[KEY_SONG_GENRE] == genre]
            if version is not None:
                records = [r for r in records if r.extras[KEY_SONG_VERSION] == version]

            if len(records) == 0:
                await interaction.followup.send("No scores found.")
                return

        if sort == "rating":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.extras.get(KEY_OVERPOWER),
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "score":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.score,
                    x.extras.get(KEY_PLAY_RATING),
                    x.extras.get(KEY_OVERPOWER),
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "overpower":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.extras.get(KEY_OVERPOWER),
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.combo_lamp.value,
                    x.clear_lamp.value,
                ),
            )
        elif sort == "overpower %":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.extras[KEY_OVERPOWER] / x.extras[KEY_OVERPOWER_MAX],
                    x.extras.get(KEY_OVERPOWER),
                    x.extras.get(KEY_PLAY_RATING),
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
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.extras.get(KEY_OVERPOWER),
                    x.clear_lamp.value,
                ),
            )
        elif sort == "clear lamp":
            records.sort(
                reverse=sort_order != "ascending",
                key=lambda x: (
                    x.clear_lamp.value,
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.extras.get(KEY_OVERPOWER),
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
                    x.extras.get(KEY_PLAY_RATING),
                    x.score,
                    x.extras.get(KEY_OVERPOWER),
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
    @flags.argument(
        "-v",
        "--version",
        required=False,
        choices=list(ChunithmVersion.__args__)
        + [v.lower() for v in ChunithmVersion.__args__],
    )
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
        version: str | None = None,
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
                not client.SUPPORTS_PERSONAL_BESTS
                and level is None
                and difficulty is None
                and genre is None
                and rank is None
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

            if level_folder is not None and client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL:
                records = await client.get_personal_bests_by_level(level_folder)
            elif (
                difficulty is not None and client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY
            ):
                records = await client.get_personal_bests_by_difficulty(difficulty)
            elif client.SUPPORTS_PERSONAL_BESTS:
                records = await client.get_personal_bests()
            else:
                if (
                    client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL
                    and client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY
                ):
                    msg = "At least one of `level` or `difficulty` must be specified."
                    exc = commands.BadArgument
                elif client.SUPPORTS_PERSONAL_BESTS_BY_LEVEL:
                    msg = "Level must be specified."
                    exc = commands.BadArgument
                elif client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY:
                    msg = "Difficulty must be specified."
                    exc = commands.BadArgument
                else:
                    msg = f"Network {client.NAME} does not support fetching personal bests."
                    exc = commands.CommandError

                raise exc(msg)

            if isinstance(client, ChunithmNet):
                # hidden chart shenanigans
                hidden_charts = await ctx.bot.database.charts.get_hidden_on_chuninet(
                    level=level, difficulty=difficulty
                )
                hidden_song_ids = {c.song_id for c in hidden_charts}
                record_charts = {(r.extras[KEY_SONG_ID], r.difficulty) for r in records}

                for song_id in hidden_song_ids:
                    # get the records for the hidden chart's song id
                    hidden_records = await client.get_personal_bests_on_song(song_id)

                    # and insert it into our records, if a record is not already there
                    records.extend(
                        [
                            r
                            for r in hidden_records
                            if (song_id, r.difficulty) not in record_charts
                        ]
                    )

            records = await self.utils.process_records(
                target_user_id, client.NAME, records
            )

            if difficulty is not None:
                records = [r for r in records if r.difficulty == difficulty]
            if rank is not None:
                records = [r for r in records if r.rank == rank]
            if level_folder is not None:
                records = [r for r in records if r.extras[KEY_LEVEL] == level_folder]
            if internal_level is not None:
                records = [
                    r
                    for r in records
                    if r.extras.get(KEY_INTERNAL_LEVEL) == internal_level
                ]
            if genre is not None:
                records = [r for r in records if r.extras[KEY_SONG_GENRE] == genre]
            if version is not None:
                version = version.upper()
                records = [r for r in records if r.extras[KEY_SONG_VERSION] == version]

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
                        sort_fn = lambda score: score.extras.get(
                            KEY_PLAY_RATING, Decimal(0)
                        )
                    elif item.startswith(("op_percent", "overpower_percent")):
                        sort_fn = lambda score: (
                            score.extras[KEY_OVERPOWER]
                            / score.extras[KEY_OVERPOWER_MAX]
                            * 100
                            if KEY_OVERPOWER in score.extras
                            and KEY_OVERPOWER_MAX in score.extras
                            else Decimal(0)
                        )
                    elif item.startswith(("op", "overpower")):
                        sort_fn = lambda score: score.extras.get(
                            KEY_OVERPOWER, Decimal(0)
                        )
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
                    lambda score: Reversor(score.extras.get(KEY_PLAY_RATING)),
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
                    lambda score: Reversor(score.extras.get(KEY_OVERPOWER)),
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
                    kamaitachi = isinstance(client, Kamaitachi)
            except commands.CommandError:
                kamaitachi = False

        async with (
            ctx.typing(),
            ctx.bot.chunithm_networks.bot_network(kamaitachi=kamaitachi) as client,
        ):
            if not client.SUPPORTS_CHART_LEADERBOARD:
                msg = f"Network {client.NAME} does not support viewing chart leaderboards."
                raise commands.CommandError(msg)

            chart = await ctx.find_chart(
                difficulty, query_str, "Select a chart to see leaderboard for:"
            )

            if chart is None:
                return

            if isinstance(client, ChunithmNet):
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
    @flags.argument(
        "-v",
        "--version",
        required=False,
        choices=list(ChunithmVersion.__args__)
        + [v.lower() for v in ChunithmVersion.__args__],
    )
    @flags.argument("-k", "--kamaitachi", action="store_true")
    @flags.argument("-o", "--omnimix", action="store_true")
    @flags.argument("--refresh", action="store_true")
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
        version: str | None = None,
        kamaitachi: bool = False,
        refresh: bool = False,
        omnimix: bool = False,
    ):
        """View statistics about a folder.

        **Parameters**:
        `user`: Discord username of the player. Yourself, if not provided.
        `level`: Level (from 1 to 15+) to search for. Can also be a level range (e.g. 14.3-14.5).
        `-d`: Difficulty to search for. Must be one of `BASIC`, `ADVANCED`, `EXPERT`, `MASTER`, `ULTIMA`, or `WE` if specified.
        `-g`: Genre to search for.
        `-v`: Version to search for.
        `-k`: Get scores from Kamaitachi, if the target user has a linked account.
        `-o`: Count removed songs towards statistics and the final count.
        `--refresh`: Force a full refresh of your scores. By default, statistics are calculated from your cached personal bests. You should only use this option if your scores are out of date.
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
            version=version.upper() if version is not None else None,
            kamaitachi=kamaitachi,
            refresh=refresh,
            omnimix=omnimix,
        )

    @app_commands.command(
        name="statistics", description="View statistics about a folder."
    )
    @app_commands.describe(
        user="The player. Yourself, if not provided.",
        level="Level (from 1 to 15+) to search for. Can also be a level range (e.g. 14.3-14.5).",
        difficulty="Difficulty to search for.",
        genre="Genre to search for.",
        version="Version to search for.",
        kamaitachi="Get scores from Kamaitachi, if the target user has a linked account.",
        refresh="Force a full refresh of your scores. By default, statistics are calculated from your cached PBs.",
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
        refresh: bool = False,
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
            refresh=refresh,
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
        refresh: bool = False,
        omnimix: bool = False,
    ):
        target_id = ctx.author.id if user is None else user.id

        async with (
            ctx.typing(),
            self.bot.begin_db_session() as session,
            self.bot.chunithm_networks.network(
                ctx, target_id, kamaitachi=kamaitachi
            ) as client,
        ):
            profile = await client.get_minimal_profile()

            if refresh:
                await ctx.respond_or_edit(
                    "Refreshing personal bests, may take some time..."
                )

                if client.SUPPORTS_RECENT_SCORES:
                    await self.utils.process_records(
                        target_id, client.NAME, await client.get_recent_scores()
                    )

                if client.SUPPORTS_PERSONAL_BESTS:
                    await self.utils.process_records(
                        target_id, client.NAME, await client.get_personal_bests()
                    )
                elif client.SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY:
                    for d in Difficulty:
                        await self.utils.process_records(
                            target_id,
                            client.NAME,
                            await client.get_personal_bests_by_difficulty(d),
                        )
                else:
                    msg = f"Network {client.NAME} does not support refreshing personal bests quickly."
                    raise commands.CommandError(msg)

            pb_query = (
                select(DBPersonalBest)
                .where(
                    (DBPersonalBest.discord_id == target_id)
                    & (DBPersonalBest.network == client.NAME)
                )
                .join(Song, DBPersonalBest.song_id == Song.id)
                .join(
                    Chart,
                    (DBPersonalBest.song_id == Chart.song_id)
                    & (DBPersonalBest.difficulty == Chart.difficulty),
                )
                .order_by(DBPersonalBest.score.desc())
            )
            chart_query = (
                select(Chart)
                .join(Song, Chart.song_id == Song.id)
                .where(Chart.song_id.not_in([50, 81]))  # basic and master tutorials
            )

            if isinstance(client, ChunithmNet):
                cond = (Song.available == True) & (Chart.available == True)  # noqa: E712
                pb_query = pb_query.where(cond)
                chart_query = chart_query.where(cond)
            elif isinstance(client, Kamaitachi):
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
        counts = Counter()

        for pb in pbs:
            pb_rank = Rank.from_score(pb.score)
            pb_combo_lamp = ComboLamp(pb.combo_lamp)
            pb_clear_lamp = ClearLamp(pb.clear_lamp)

            for rank in (Rank.s, Rank.sp, Rank.ss, Rank.ssp, Rank.sss, Rank.sssp):
                if pb_rank.value >= rank.value:
                    counts[rank] += 1

            for combo_lamp in ComboLamp:
                if combo_lamp == ComboLamp.none:
                    continue

                if pb_combo_lamp.value >= combo_lamp.value:
                    counts[combo_lamp] += 1

            for clear_lamp in ClearLamp:
                if clear_lamp == ClearLamp.failed:
                    continue

                if pb_clear_lamp.value >= clear_lamp.value:
                    counts[clear_lamp] += 1

        embed = discord.Embed(
            color=discord.Color.yellow(),
            title=f"{escape_markdown(profile.username)}'s folder statistics",
            timestamp=max(
                (pb.last_played_at for pb in pbs if pb.last_played_at is not None),
                default=None,
            ),
        )
        embed.set_footer(
            text=(
                f"Use `{ctx.clean_prefix}{ctx.invoked_with} --refresh` if statistics seem wrong."
                if ctx.interaction is None
                else "Use `/statistics refresh:True` if statistics seem wrong."
            )
        )

        description_parts: list[str] = []

        if level is not None:
            description_parts.append(f"Level {level}")

        if difficulty is not None:
            description_parts.append(str(difficulty))

        if genre is not None:
            description_parts.append(str(genre))

        if version is not None:
            description_parts.append(version)

        embed.description = ", ".join(description_parts)

        embed.add_field(
            name="Played",
            value=f"{len(pbs)} / {chart_count} ({percentage_played:.2f}%)",
            inline=difficulty != Difficulty.worlds_end,
        )

        if difficulty != Difficulty.worlds_end:
            charts_by_id_difficulty: dict[tuple[int, str], Chart] = {}
            op_by_song: dict[int, Decimal] = {}
            pb_op_by_song: dict[int, Decimal] = {}

            for chart in charts:
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
                    calculate_play_overpower(
                        calculate_overpower_base(pb.score, chart.const),
                        pb_combo_lamp,
                    ),
                )

            op = floor_to_ndp(sum(pb_op_by_song.values(), Decimal(0)), 2)
            total_op = floor_to_ndp(sum(op_by_song.values(), Decimal(0)), 2)
            op_percent = (
                floor_to_ndp(op * 100 / total_op, 2) if total_op > 0 else Decimal(0)
            )

            embed.add_field(
                name="OVER POWER",
                value=f"{op} / {total_op} ({op_percent:.2f}%)",
            )

        embed.add_field(name="\u3000", value="\u3000")
        embed.add_field(
            name="Average score (played)",
            value=f"{int(statistics.fmean(pb.score for pb in pbs)) if len(pbs) > 0 else 0}",
        )
        embed.add_field(
            name="Average score (all)",
            value=f"{int(sum(pb.score for pb in pbs) / chart_count)}",
        )
        embed.add_field(name="\u3000", value="\u3000")
        embed.add_field(
            name="Ranks",
            value="\n".join(
                [
                    f"{config.icons.rank_icon(rank)} ▸ {counts[rank]}"
                    for rank in (
                        Rank.sssp,
                        Rank.sss,
                        Rank.ssp,
                        Rank.ss,
                        Rank.sp,
                        Rank.s,
                    )
                ]
            ),
        )
        embed.add_field(
            name="Combo lamps",
            value="\n".join(
                reversed(
                    [
                        f"{combo_lamp.short()} ▸ {counts[combo_lamp]}"
                        for combo_lamp in ComboLamp
                        if combo_lamp != ComboLamp.none
                    ]
                )
            ),
        )
        embed.add_field(
            name="Clear lamps",
            value="\n".join(
                reversed(
                    [
                        f"{clear_lamp.short()} ▸ {counts[clear_lamp]}"
                        for clear_lamp in ClearLamp
                        if clear_lamp != ClearLamp.failed
                    ]
                )
            ),
        )
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


async def setup(bot: "ChuniBot"):
    await bot.add_cog(RecordsCog(bot))
