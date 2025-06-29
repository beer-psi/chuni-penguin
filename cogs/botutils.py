import contextlib
import io
import sys
from dataclasses import dataclass
from http.cookiejar import LWPCookieJar
from typing import TYPE_CHECKING, Literal, Optional, Sequence, TypeVar

import httpx
import msgspec
from discord import Interaction
from discord.ext import commands, tasks
from discord.ext.commands import Context
from discord.utils import MISSING
from rapidfuzz import fuzz, process
from sqlalchemy import select, update
from sqlalchemy.orm import contains_eager, joinedload

from chunithm_net import ChuniNet
from chunithm_net.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER_BASE,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_SONG_GENRE,
    KEY_SONG_ID,
    KEY_SONG_VERSION,
    KEY_TOTAL_COMBO,
)
from chunithm_net.models.enums import Genres, Rank
from chunithm_net.models.record import Record
from database.models import Alias, Cookie, Song, UserConfig
from utils import get_jacket_url
from utils.calculation.overpower import (
    calculate_overpower_base,
    calculate_overpower_max,
)
from utils.calculation.rating import calculate_rating
from utils.config import config
from utils.logging import logger
from utils.types import MissingDetailedParams

if TYPE_CHECKING:
    from bot import ChuniBot

T = TypeVar("T", bound=Record)


class CachedAlias:
    id: Optional[int] = None
    alias: str
    title: str
    song_id: int
    guild_id: Optional[int] = None

    def __init__(
        self,
        id: Optional[int],
        alias: str,
        title: str,
        song_id: int,
        guild_id: Optional[int],
    ) -> None:
        self.id = id
        self.alias = alias
        self.title = title
        self.song_id = song_id
        self.guild_id = guild_id


@dataclass
class SongSearchResult:
    songs: list[Song]
    matched_alias: Optional[Alias]
    similarity: float


class KeiyoushiUserAgents(msgspec.Struct):
    recommended: str
    desktop: list[str]
    mobile: list[str]


class UtilsCog(commands.Cog, name="Utils"):
    def __init__(self, bot: "ChuniBot") -> None:
        self.bot = bot

        # guild_id: list of aliases
        self.alias_cache: dict[int, list[CachedAlias]] = {}
        self.user_agents: KeiyoushiUserAgents = MISSING

        # user_id: (refcount, ChuniNet)
        self._chuni_net_sessions: dict[int, tuple[int, ChuniNet]] = {}

    async def cog_load(self) -> None:
        self._update_user_agents.start()
        await self._reload_alias_cache()

    async def cog_unload(self) -> None:
        self._update_user_agents.stop()

    @tasks.loop(hours=24)
    async def _update_user_agents(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://keiyoushi.github.io/user-agents/user-agents.min.json"
            )

            if resp.status_code != 200:
                logger.warning(
                    "could not update user agents",
                    tag="update_user_agent_failed",
                    status_code=resp.status_code,
                )
                return

            try:
                self.user_agents = msgspec.json.decode(
                    resp.content, type=KeiyoushiUserAgents
                )
                logger.debug(
                    "updated user agents",
                    tag="update_user_agent_success",
                    count=len(self.user_agents.desktop)
                    + len(self.user_agents.mobile)
                    + 1,  # for recommended UA
                )
            except msgspec.DecodeError as e:
                logger.exception(
                    "could not parse user agents",
                    tag="update_user_agent_failed",
                    exc_info=e,
                )
                return

    @_update_user_agents.error
    async def _update_user_agents_error(self, exc: BaseException):
        logger.exception(
            "unhandled exception updating user agents",
            tag="update_useragent_failed",
            exc_info=exc,
        )

    async def _reload_alias_cache(self) -> None:
        async with self.bot.begin_db_session() as session:
            stmt = select(Song).options(joinedload(Song.aliases))
            songs = (await session.execute(stmt)).scalars().unique()

        self.alias_cache.clear()

        titles = set()
        global_aliases = self.alias_cache.setdefault(-1, [])

        for song in songs:
            title_lower = song.title.lower()

            if title_lower not in titles:
                titles.add(title_lower)

                global_aliases.append(
                    CachedAlias(None, title_lower, song.title, song.id, -1)
                )

            for alias in song.aliases:
                guild_aliases = self.alias_cache.setdefault(alias.guild_id, [])

                guild_aliases.append(
                    CachedAlias(
                        alias.rowid,
                        alias.alias.lower(),
                        song.title,
                        alias.song_id,
                        alias.guild_id,
                    )
                )

    async def guild_prefix(self, ctx: Context) -> str:
        default_prefix: str = config.bot.default_prefix
        if ctx.guild is None:
            return default_prefix

        return self.bot.prefixes.get(ctx.guild.id, default_prefix)

    def _get_not_logged_in_message(
        self,
        network: Literal["kamaitachi", "chuninet"] | None,
        author_id: int,
        target_id: int,
        *,
        is_interaction: bool,
    ):
        if network == "kamaitachi":
            network_name = " to Kamaitachi"
            command_name = "kamaitachi link"
        elif network == "chuninet":
            network_name = " to CHUNITHM-NET"
            command_name = "login"
        elif network is None:
            network_name = ""
            command_name = "login"
        else:
            msg = f"Unknown network: {network}"
            raise ValueError(msg)

        if author_id == target_id:
            return f"You are not logged in{network_name}. Please send `{'/' if is_interaction else config.bot.default_prefix}{command_name}` in my DMs to log in."

        return f"<@{target_id}> is not logged in{network_name}."

    async def login_check(
        self,
        author_id: int,
        target_id: int | None = None,
        *,
        is_interaction: bool = False,
    ) -> LWPCookieJar:
        target_id = target_id or author_id
        clal = await self.fetch_cookie(target_id)
        user_config = await self.fetch_user_config(target_id)

        if clal is None or (user_config.privacy_mode and author_id != target_id):
            msg = self._get_not_logged_in_message(
                "chuninet", author_id, target_id, is_interaction=is_interaction
            )
            raise commands.CommandError(msg)

        return clal

    async def fetch_user_config(self, id: int) -> UserConfig:
        async with self.bot.begin_db_session() as session:
            stmt = select(UserConfig).where(UserConfig.discord_id == id)
            return (await session.execute(stmt)).scalar_one_or_none() or UserConfig(
                discord_id=id, synthesis_alt_jacket="default", privacy_mode=False
            )

    async def fetch_cookie(self, id: int) -> LWPCookieJar | None:
        async with self.bot.begin_db_session() as session:
            stmt = select(Cookie).where(Cookie.discord_id == id)
            cookie = (await session.execute(stmt)).scalar_one_or_none()

        if cookie is None or not cookie.cookie.startswith("#LWP-Cookies-2.0"):
            return None

        jar = LWPCookieJar()
        jar._really_load(  # type: ignore[reportAttributeAccessIssue]
            io.StringIO(cookie.cookie), "?", ignore_discard=False, ignore_expires=False
        )

        return jar

    @contextlib.asynccontextmanager
    async def chuninet(self, ctx: Context | Interaction, id: int | None = None):
        author_id = ctx.author.id if isinstance(ctx, Context) else ctx.user.id
        target_id = id or author_id
        is_interaction = isinstance(ctx, Interaction) or ctx.interaction is not None
        user_config = await self.fetch_user_config(target_id)

        if user_config.privacy_mode and author_id != target_id:
            msg = self._get_not_logged_in_message(
                "chuninet", author_id, target_id, is_interaction=is_interaction
            )
            raise commands.CommandError(msg)

        if (
            target_id in self._chuni_net_sessions
            and self._chuni_net_sessions[target_id][0] != 0
        ):
            refcount, session = self._chuni_net_sessions[target_id]
            logger.debug(
                "Using cached CHUNITHM-NET session",
                tag="cached_chunithm_net_session",
                refcount=refcount,
            )
        else:
            jar = await self.fetch_cookie(target_id)

            if jar is None:
                msg = self._get_not_logged_in_message(
                    "chuninet", author_id, target_id, is_interaction=is_interaction
                )
                raise commands.CommandError(msg)

            session = ChuniNet(jar)
            refcount = 0

            session.session.headers["user-agent"] = self.user_agents.desktop[
                (target_id >> 22) % len(self.user_agents.desktop)
            ]

        try:
            self._chuni_net_sessions[target_id] = (refcount + 1, session)
            yield session
        finally:
            refcount, session = self._chuni_net_sessions[target_id]
            refcount -= 1

            if refcount == 0:
                async with self.bot.begin_db_session() as db_session:
                    await db_session.execute(
                        update(Cookie)
                        .where(Cookie.discord_id == target_id)
                        .values(
                            cookie=f"#LWP-Cookies-2.0\n{session.session._cookies.jar.as_lwp_str()}"  # pyright: ignore[reportAttributeAccessIssue]
                        )
                    )
                    await db_session.commit()

                await session.close()

                del self._chuni_net_sessions[target_id]
            else:
                self._chuni_net_sessions[target_id] = refcount, session

    @contextlib.asynccontextmanager
    async def kamaitachi_client(
        self, ctx: Context | Interaction, id: int | None = None
    ):
        author_id = ctx.author.id if isinstance(ctx, Context) else ctx.user.id
        target_id = id or author_id
        is_interaction = isinstance(ctx, Interaction) or ctx.interaction is not None
        user_config = await self.fetch_user_config(target_id)

        async with self.bot.begin_db_session() as session:
            cookie = await session.scalar(
                select(Cookie).where(Cookie.discord_id == target_id)
            )

            if (
                cookie is None
                or cookie.kamaitachi_token is None
                or (user_config.privacy_mode and author_id != target_id)
            ):
                msg = msg = self._get_not_logged_in_message(
                    "kamaitachi", author_id, target_id, is_interaction=is_interaction
                )
                raise commands.CommandError(msg)

        client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            transport=httpx.AsyncHTTPTransport(retries=5),
        )
        client.headers["Authorization"] = f"Bearer {cookie.kamaitachi_token}"
        client.headers["User-Agent"] = (
            f"chuni-penguin (+https://github.com/beer-psi/chuni-penguin) Python/{sys.version_info[0]}.{sys.version_info[1]} httpx/{httpx.__version__}"
        )

        async with client:
            yield client

    async def choose_preferred_network(
        self,
        ctx: Context | Interaction,
        id: int | None = None,
        *,
        kamaitachi: bool = False,
    ):
        author_id = ctx.author.id if isinstance(ctx, Context) else ctx.user.id
        target_id = id or author_id
        is_interaction = isinstance(ctx, Interaction) or ctx.interaction is not None
        user_config = await self.fetch_user_config(target_id)

        async with self.bot.begin_db_session() as session:
            stmt = select(Cookie).where(Cookie.discord_id == target_id)
            cookie = (await session.execute(stmt)).scalar_one_or_none()

            if cookie is None or (user_config.privacy_mode and author_id != target_id):
                msg = self._get_not_logged_in_message(
                    None, author_id, target_id, is_interaction=is_interaction
                )
                raise commands.CommandError(msg)

            if kamaitachi:
                if cookie.kamaitachi_token is None:
                    msg = self._get_not_logged_in_message(
                        "kamaitachi",
                        author_id,
                        target_id,
                        is_interaction=is_interaction,
                    )
                    raise commands.CommandError(msg)

                return "kamaitachi"

            if cookie.cookie.startswith("#LWP-Cookies-2.0"):
                return "chuninet"

            if cookie.kamaitachi_token is not None:
                return "kamaitachi"

            msg = self._get_not_logged_in_message(
                None, author_id, target_id, is_interaction=is_interaction
            )
            raise commands.CommandError(msg)

    async def hydrate_records(self, records: Sequence[T]) -> list[T]:
        song_ids = set()
        jackets = set()

        for record in records:
            song_id = record.extras.get(KEY_SONG_ID)

            if song_id is not None:
                if song_id == 723:
                    # sega revived an old song under a different ID for whatever reason, and people have scores on both of them.
                    # we only have scores on ID 808 though. this is quite a bodge.
                    song_id = 808
                    record.extras[KEY_SONG_ID] = 808

                song_ids.add(song_id)
            elif record.jacket is not None:
                jackets.add(record.jacket.split("/")[-1])
            else:
                raise MissingDetailedParams

        async with self.bot.begin_db_session() as session:
            stmt = (
                select(Song)
                .where(Song.id.in_(song_ids) | Song.jacket.in_(jackets))
                .options(joinedload(Song.charts))
            )
            songs = (await session.execute(stmt)).scalars().unique()

        song_lookup: dict[int | str, Song] = {}

        for song in songs:
            song_lookup[song.id] = song
            song_lookup[song.jacket] = song

        hydrated_records = []

        for record in records[:]:
            song_id = record.extras.get(KEY_SONG_ID)

            if song_id is not None:
                song = song_lookup.get(song_id)
            elif record.jacket is not None:
                song = song_lookup.get(record.jacket.split("/")[-1])
            else:
                raise MissingDetailedParams

            if song is None:
                await logger.awarning(
                    "Missing song data",
                    tag="missing_song_data",
                    title=record.title,
                )
                hydrated_records.append(record)
                continue

            if song_id is None:
                record.extras[KEY_SONG_ID] = song.id

            if KEY_SONG_VERSION not in record.extras:
                record.extras[KEY_SONG_VERSION] = song.version

            if record.jacket is None:
                record.jacket = get_jacket_url(song)

            chart = next(
                (
                    c
                    for c in song.charts
                    if c.difficulty == record.difficulty.short_form()
                ),
                None,
            )

            if chart is None:
                await logger.awarning(
                    "Missing chart data",
                    tag="missing_chart_data",
                    song_id=song.id,
                    difficulty=record.difficulty,
                )
                hydrated_records.append(record)
                continue

            if KEY_LEVEL not in record.extras:
                record.extras[KEY_LEVEL] = chart.level

            if (internal_level := record.extras.get(KEY_INTERNAL_LEVEL)) is None:
                if chart.const is None:
                    try:
                        internal_level = record.extras[KEY_INTERNAL_LEVEL] = float(
                            chart.level.replace("+", ".5")
                        )
                    except ValueError:
                        internal_level = record.extras[KEY_INTERNAL_LEVEL] = 0
                else:
                    internal_level = record.extras[KEY_INTERNAL_LEVEL] = chart.const

            if KEY_PLAY_RATING not in record.extras:
                record.extras[KEY_PLAY_RATING] = calculate_rating(
                    record.score, internal_level
                )

            if KEY_OVERPOWER_BASE not in record.extras:
                record.extras[KEY_OVERPOWER_BASE] = calculate_overpower_base(
                    record.score, internal_level
                )

            if KEY_OVERPOWER_MAX not in record.extras:
                record.extras[KEY_OVERPOWER_MAX] = calculate_overpower_max(
                    internal_level
                )

            if KEY_TOTAL_COMBO not in record.extras and chart.maxcombo is not None:
                record.extras[KEY_TOTAL_COMBO] = chart.maxcombo

            if record.rank == Rank.D:
                record.rank = Rank.from_score(record.score)

            if KEY_SONG_GENRE not in record.extras:
                record.extras[KEY_SONG_GENRE] = Genres(song.chunithm_catcode)

            hydrated_records.append(record)

        return hydrated_records

    async def hydrate_record(self, record: T) -> T:
        return (await self.hydrate_records([record]))[0]

    async def find_song(
        self,
        query: str,
        *,
        guild_id: Optional[int] = None,
        worlds_end: bool = False,
    ) -> tuple[Song | None, Alias | None, float]:
        """Finds the song that best matches a given query.

        Parameters
        ----------
        query: str
            The query to search for.
        guild_id: Optional[int]
            The ID of the guild to search for aliases in. If None, only global aliases are searched.
        worlds_end: bool
            Whether to search for WORLD'S END charts, instead of normal charts.

        Returns
        -------
        tuple[Song, Alias | None, float]
            The third item is the similarity of the matched song.
        """
        aliases = self.alias_cache[-1][:]

        if (
            guild_id is not None
            and (guild_aliases := self.alias_cache.get(guild_id)) is not None
        ):
            aliases.extend(guild_aliases)

        (_, similarity, index) = process.extractOne(
            query, [x.alias for x in aliases], scorer=fuzz.QRatio
        )
        matching_alias = aliases[index]

        async with self.bot.begin_db_session() as session:
            condition = Song.id == matching_alias.song_id

            if worlds_end:
                condition = (Song.title == matching_alias.title) & (
                    Song.genre == "WORLD'S END"
                )

            stmt = select(Song).where(condition)
            song = (await session.execute(stmt)).scalar_one_or_none()

            if matching_alias.id is not None:
                stmt = select(Alias).where(Alias.rowid == matching_alias.id)
                alias = (await session.execute(stmt)).scalar_one_or_none()
            else:
                alias = None

        return song, alias, similarity

    async def find_songs(
        self,
        query: str,
        *,
        guild_id: Optional[int] = None,
        available: Optional[bool] = None,
        load_charts: bool = False,
        load_global_aliases: bool = False,
    ) -> SongSearchResult:
        aliases = self.alias_cache[-1][:]

        if (
            guild_id is not None
            and (guild_aliases := self.alias_cache.get(guild_id)) is not None
        ):
            aliases.extend(guild_aliases)

        (_, similarity, index) = process.extractOne(
            query, [x.alias for x in aliases], scorer=fuzz.QRatio
        )
        matching_alias = aliases[index]

        async with self.bot.begin_db_session() as session:
            cond = Song.title == matching_alias.title

            if available is not None:
                cond &= Song.available == available

            stmt = select(Song).where(cond)

            if load_charts:
                stmt = stmt.options(joinedload(Song.charts))

            if load_global_aliases:
                stmt = stmt.outerjoin(
                    Alias, (Alias.song_id == Song.id) & (Alias.guild_id == -1)
                ).options(contains_eager(Song.aliases))

            songs = (await session.execute(stmt)).scalars().unique()

            if matching_alias.id is not None:
                stmt = select(Alias).where(Alias.rowid == matching_alias.id)
                alias = (await session.execute(stmt)).scalar_one_or_none()
            else:
                alias = None

        return SongSearchResult(
            songs=list(songs), matched_alias=alias, similarity=similarity
        )


async def setup(bot: "ChuniBot"):
    await bot.add_cog(UtilsCog(bot))
