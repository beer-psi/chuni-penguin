from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional, Sequence, TypeVar

import msgspec
from discord.ext import commands
from discord.ext.commands import Context
from rapidfuzz import fuzz, process
from sqlalchemy import select, update
from sqlalchemy.orm import contains_eager, joinedload

from chuni_penguin.calculation import (
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
    calculate_rating,
)
from chuni_penguin.config import config
from chuni_penguin.database import Alias, Chart, Cookie, Song, UserConfig
from chuni_penguin.database import PersonalBest as DBPersonalBest
from chuni_penguin.logging import logger
from chuni_penguin.networks.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_OVERPOWER,
    KEY_OVERPOWER_MAX,
    KEY_PLAY_RATING,
    KEY_SONG_GENRE,
    KEY_SONG_ID,
    KEY_SONG_VERSION,
    KEY_TOTAL_COMBO,
)
from chuni_penguin.networks.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Difficulty,
    Genre,
    Judgements,
    Rank,
    Score,
)
from chuni_penguin.networks.types import PersonalBest as NetworkPersonalBest
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

    async def hydrate_records(self, records: Sequence[T]) -> list[T]:
        song_ids = set()
        jackets = set()
        titles = set()

        for record in records:
            song_id = record.extras.get(KEY_SONG_ID)

            if song_id is not None:
                if song_id == 723:
                    # sega revived an old song under a different ID for whatever reason, and people have scores on both of them.
                    # we only have scores on ID 808 though. this is quite a bodge.
                    song_id = 808
                    record.extras[KEY_SONG_ID] = 808

                song_ids.add(song_id)
            elif record.jacket_url is not None:
                jackets.add(record.jacket_url.split("/")[-1])
            else:
                titles.add(record.title)

        async with self.bot.begin_db_read() as session:
            stmt = (
                select(Song)
                .where(
                    Song.id.in_(song_ids)
                    | Song.jacket.in_(jackets)
                    # Not resolving WE charts on title since there can be multiple
                    # of them and I'm not dealing with that shit
                    | ((Song.id < 8000) & Song.title.in_(titles))
                )
                .options(joinedload(Song.charts))
            )
            songs = (await session.execute(stmt)).scalars().unique()

        song_lookup: dict[int | str, Song] = {}

        for song in songs:
            song_lookup[song.id] = song
            song_lookup[song.jacket] = song
            song_lookup[song.title] = song

        hydrated_records = []

        for record in records[:]:
            song_id = record.extras.get(KEY_SONG_ID)

            if song_id is not None:
                song = song_lookup.get(song_id)
            elif record.jacket_url is not None:
                song = song_lookup.get(record.jacket_url.split("/")[-1])
            else:
                song = song_lookup.get(record.title)

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

            if not record.title:
                record.title = song.title

            if record.jacket_url is None:
                record.jacket_url = get_jacket_url(song)

            chart = next(
                (c for c in song.charts if c.difficulty == record.difficulty.short()),
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

            if KEY_OVERPOWER not in record.extras:
                record.extras[KEY_OVERPOWER] = calculate_play_overpower(
                    calculate_overpower_base(record.score, internal_level),
                    record.combo_lamp,
                )

            if KEY_OVERPOWER_MAX not in record.extras:
                record.extras[KEY_OVERPOWER_MAX] = calculate_overpower_max(
                    internal_level
                )

            if KEY_SONG_GENRE not in record.extras:
                record.extras[KEY_SONG_GENRE] = Genre(song.chunithm_catcode)

            # Hydrate maxcombo and judgement data when possible.
            if chart.maxcombo is not None:
                if KEY_TOTAL_COMBO not in record.extras:
                    record.extras[KEY_TOTAL_COMBO] = chart.maxcombo

                if record.max_combo is None and record.combo_lamp in (
                    ComboLamp.full_combo,
                    ComboLamp.all_justice,
                    ComboLamp.all_justice_critical,
                ):
                    record.max_combo = chart.maxcombo

                if record.judgements is None:
                    if record.combo_lamp == ComboLamp.all_justice_critical:
                        record.judgements = Judgements(
                            justice_critical=chart.maxcombo, justice=0, attack=0, miss=0
                        )
                    elif record.combo_lamp == ComboLamp.all_justice:
                        # (notecount * 101) - ((notecount * 101) * score / 1010000)
                        justice = int(chart.maxcombo * (1010000 - record.score) / 10000)
                        record.judgements = Judgements(
                            justice_critical=chart.maxcombo - justice,
                            justice=justice,
                            attack=0,
                            miss=0,
                        )

            hydrated_records.append(record)

        return hydrated_records

    async def process_record(self, discord_id: int, network: str, record: T) -> T:
        return (await self.process_records(discord_id, network, [record]))[0]

    async def process_records(
        self, discord_id: int, network: str, records: Sequence[T]
    ) -> list[T]:
        hydrated_records = await self.hydrate_records(records)
        db_records = await self.bot.database.personal_bests.upsert_personal_bests(
            discord_id, network, hydrated_records
        )
        db_records_by_chart = {(r.song_id, r.difficulty): r for r in db_records}

        # Annotate hydrated records with PB stored in database when applicable.
        # The returned DB records are better than or equal to the records we're trying
        # to hydrate, since they're personal bests.
        for record in hydrated_records:
            try:
                db_record = db_records_by_chart[
                    (record.extras[KEY_SONG_ID], record.difficulty.short())
                ]
            except KeyError:
                continue

            # Only annotate data if the record has the same score as the stored PB.
            if record.score != db_record.score:
                continue

            if (
                record.judgements is None
                and db_record.justice_critical is not None
                and db_record.justice is not None
                and db_record.attack is not None
                and db_record.miss is not None
            ):
                record.judgements = Judgements(
                    justice_critical=db_record.justice_critical,
                    justice=db_record.justice,
                    attack=db_record.attack,
                    miss=db_record.miss,
                )

            if record.achieved_at is None and db_record.achieved_at is not None:
                record.achieved_at = db_record.achieved_at

            if record.clear_lamp is None:
                record.clear_lamp = ClearLamp(db_record.clear_lamp)

            if record.combo_lamp is None:
                record.combo_lamp = ComboLamp(db_record.combo_lamp)

            if record.chain_lamp is None and db_record.chain_lamp is not None:
                record.chain_lamp = ChainLamp(db_record.chain_lamp)

            if record.max_combo is None and db_record.max_combo is not None:
                record.max_combo = db_record.max_combo

        return hydrated_records

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

        # Since we don't define a score_cutoff here, there's no possible way for
        # process.extractOne to return None. This is true as of RapidFuzz 3.14.3,
        # and in earlier versions this did not raise a type error.
        (_, similarity, index) = process.extractOne(  # pyright: ignore[reportGeneralTypeIssues]
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

        # Since we don't define a score_cutoff here, there's no possible way for
        # process.extractOne to return None. This is true as of RapidFuzz 3.14.3,
        # and in earlier versions this did not raise a type error.
        (_, similarity, index) = process.extractOne(  # pyright: ignore[reportGeneralTypeIssues]
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

        pb = NetworkPersonalBest(
            title=chart.song.title,
            difficulty=Difficulty(chart.difficulty),
            score=db_pb.score,
            jacket_url=get_jacket_url(chart.song),
            rank=Rank.from_score(db_pb.score),
            clear_lamp=ClearLamp(db_pb.clear_lamp),
            combo_lamp=ComboLamp(db_pb.combo_lamp),
            chain_lamp=(
                ChainLamp(db_pb.chain_lamp) if db_pb.chain_lamp is not None else None
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
        )
        pb.extras[KEY_SONG_ID] = db_pb.song_id

        return (await self.hydrate_records([pb]))[0]


async def setup(bot: "ChuniBot"):
    await bot.add_cog(UtilsCog(bot))
