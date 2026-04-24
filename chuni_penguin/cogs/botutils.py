from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Optional, TypeVar

import msgspec
from discord.ext import commands
from discord.ext.commands import Context
from rapidfuzz import fuzz, process
from sqlalchemy import select, update
from sqlalchemy.orm import contains_eager, joinedload

from chuni_penguin.adapters.utils import hydrate_records
from chuni_penguin.config import config
from chuni_penguin.database import Alias, Chart, Cookie, Song, UserConfig
from chuni_penguin.database import PersonalBest as DBPersonalBest
from chuni_penguin.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Difficulty,
    Genre,
    Judgements,
    Rank,
    Score,
)
from chuni_penguin.types import Chart as NetworkChart
from chuni_penguin.types import PersonalBest as NetworkPersonalBest
from chuni_penguin.types import Song as NetworkSong
from chuni_penguin.utils import get_jacket_url

if TYPE_CHECKING:
    from chuni_penguin.bot import ChuniBot

T = TypeVar("T", bound=Score)


class CachedAlias:
    __slots__ = ("alias", "guild_id", "id", "song_id", "title")

    def __init__(
        self,
        id: Optional[int],
        alias: str,
        title: str,
        song_id: int,
        guild_id: int,
    ) -> None:
        self.id = id
        self.alias = alias
        self.title = title
        self.song_id = song_id
        self.guild_id = guild_id


@dataclass(slots=True)
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

    async def cog_load(self) -> None:
        await self._reload_alias_cache()

    async def _reload_alias_cache(self) -> None:
        async with self.bot.begin_db_read() as session:
            stmt = select(Song).options(joinedload(Song.aliases))
            songs = (await session.execute(stmt)).scalars().unique().all()

        self.alias_cache.clear()

        titles = set()
        global_aliases = self.alias_cache.setdefault(0, [])

        for song in songs:
            title_lower = song.title.lower()

            if title_lower not in titles:
                titles.add(title_lower)

                global_aliases.append(
                    CachedAlias(None, title_lower, song.title, song.id, 0)
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

        for song in songs:
            artist_lower = song.artist.lower()

            if artist_lower not in titles:
                titles.add(artist_lower)

                global_aliases.append(
                    CachedAlias(None, artist_lower, song.title, song.id, 0)
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
    ) -> str:
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
        async with self.bot.begin_db_read() as session:
            stmt = select(UserConfig).where(UserConfig.discord_id == id)
            return (await session.execute(stmt)).scalar_one_or_none() or UserConfig(
                discord_id=id, synthesis_alt_jacket="default", privacy_mode=False
            )

    async def fetch_cookie(self, id: int) -> str | None:
        async with self.bot.begin_db_read() as session:
            stmt = select(Cookie).where(Cookie.discord_id == id)
            cookie = (await session.execute(stmt)).scalar_one_or_none()

        if cookie is None or not cookie.cookie.startswith("#LWP-Cookies-2.0"):
            return None

        return cookie.cookie

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
        aliases = self.alias_cache[0][:]

        if (
            guild_id is not None
            and (guild_aliases := self.alias_cache.get(guild_id)) is not None
        ):
            aliases.extend(guild_aliases)

        (_, similarity, index) = process.extractOne(
            query.lower(), [x.alias for x in aliases], scorer=fuzz.QRatio
        )
        matching_alias = aliases[index]

        async with self.bot.begin_db_read() as session:
            condition = Song.id == matching_alias.song_id

            if worlds_end:
                condition = (Song.title == matching_alias.title) & (
                    Song.genre == "WORLD'S END"
                )

            stmt = select(Song).where(condition)
            song = (await session.execute(stmt)).scalar_one_or_none()

        if matching_alias.id is not None:
            stmt = (
                update(Alias)
                .where(Alias.rowid == matching_alias.id)
                .values(uses=Alias.uses + 1)
                .returning(Alias)
            )
            alias = (await self.bot.database.writer.execute(stmt)).scalar_one()
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
        aliases = self.alias_cache[0][:]

        if (
            guild_id is not None
            and (guild_aliases := self.alias_cache.get(guild_id)) is not None
        ):
            aliases.extend(guild_aliases)

        (_, similarity, index) = process.extractOne(
            query.lower(), [x.alias for x in aliases], scorer=fuzz.QRatio
        )
        matching_alias = aliases[index]

        async with self.bot.begin_db_read() as session:
            cond = Song.title == matching_alias.title

            if available is not None:
                cond &= Song.available == available

            stmt = select(Song).where(cond)

            if load_charts:
                stmt = stmt.options(joinedload(Song.charts))

            if load_global_aliases:
                stmt = stmt.outerjoin(
                    Alias, (Alias.song_id == Song.id) & (Alias.guild_id == 0)
                ).options(contains_eager(Song.aliases))

            songs = (await session.execute(stmt)).scalars().unique()

        if matching_alias.id is not None:
            stmt = (
                update(Alias)
                .where(Alias.rowid == matching_alias.id)
                .values(uses=Alias.uses + 1)
                .returning(Alias)
            )
            alias = (await self.bot.database.writer.execute(stmt)).scalar_one_or_none()
        else:
            alias = None

        return SongSearchResult(
            songs=list(songs), matched_alias=alias, similarity=similarity
        )

    async def convert_to_network_pb(self, db_pb: DBPersonalBest):
        async with self.bot.begin_db_read() as session:
            query = (
                select(Chart)
                .where(
                    (Chart.song_id == db_pb.song_id)
                    & (Chart.difficulty == db_pb.difficulty)
                )
                .options(joinedload(Chart.song))
            )
            chart = (await session.execute(query)).scalar_one()

        network_song = NetworkSong(
            id=chart.song.id,
            title=chart.song.title,
            version=chart.song.version,
            genre=Genre(chart.song.chunithm_catcode),
            jacket_url=get_jacket_url(chart.song),
        )
        network_chart = NetworkChart(
            difficulty=Difficulty(chart.difficulty),
            level=chart.level,
            internal_level=chart.const,
            max_combo=chart.maxcombo,
        )
        pb = NetworkPersonalBest(
            song=network_song,
            chart=network_chart,
            score=db_pb.score,
            rank=Rank.from_score(db_pb.score),
            clear_lamp=ClearLamp(db_pb.clear_lamp),
            combo_lamp=ComboLamp(db_pb.combo_lamp),
            chain_lamp=(
                ChainLamp(db_pb.chain_lamp)
                if db_pb.chain_lamp is not None
                else ChainLamp.none
            ),
            achieved_at=db_pb.achieved_at,
            max_combo=db_pb.max_combo,
            judgements=(
                Judgements(
                    justice_critical=db_pb.justice_critical,
                    justice=db_pb.justice,
                    attack=db_pb.attack,
                    miss=db_pb.miss,
                )
                if db_pb.justice_critical is not None
                and db_pb.justice is not None
                and db_pb.attack is not None
                and db_pb.miss is not None
                else None
            ),
            rating=Decimal(db_pb.rating) / 100 if db_pb.rating is not None else None,
            overpower=(
                Decimal(db_pb.overpower) / 1000 if db_pb.overpower is not None else None
            ),
        )
        return (await hydrate_records(self.bot.database, [pb]))[0]


async def setup(bot: "ChuniBot"):
    await bot.add_cog(UtilsCog(bot))
