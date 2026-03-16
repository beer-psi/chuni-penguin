import contextlib
import enum
import json
import operator
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import discord
import msgspec
import yarl
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    delete,
    exists,
    select,
    true,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import contains_eager, joinedload
from structlog.stdlib import BoundLogger

from chuni_penguin.config import GitSeedsConfig, LocalSeedsConfig, config
from chuni_penguin.constants import ChunithmVersion
from chuni_penguin.database import (
    Alias,
    Chart,
    Course,
    CourseTrack,
    LinkedGate,
    LinkedGateCondition,
    SdvxinChartView,
    Song,
    SongJacket,
    course_track_charts,
)
from chuni_penguin.networks.types import CourseClass, Difficulty, Genre, LinkLevel

if TYPE_CHECKING:
    from sqlalchemy.sql._typing import _DMLTableArgument

SEEDS_DIR = Path(__file__).parent.parent / "chuni_penguin" / "database" / "seeds"


class SeedsJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, (enum.Enum, discord.Enum)):
            return o.name

        if isinstance(o, datetime):
            return o.astimezone(UTC).isoformat()

        return super().default(o)


class SeedsSdvxin(msgspec.Struct):
    id: str
    end_index: str

    def __post_init__(self):
        if not self.id.isdigit():
            msg = f"ID is not a numeric string, got {self.id}"
            raise ValueError(msg)

        if len(self.end_index) > 0 and not self.end_index.isdigit():
            msg = f"WE index is not a numeric string, got {self.end_index}"
            raise ValueError(msg)


def msgspec_dec_hook(t: type, obj: Any) -> Any:
    if t is Difficulty and isinstance(obj, str):
        return t(obj)

    if issubclass(t, (enum.Enum, discord.Enum)) and isinstance(obj, str):
        return getattr(t, obj)

    if issubclass(t, (enum.Enum, discord.Enum)) and isinstance(obj, int):
        return t(obj)

    msg = f"dec_hook not implemented to decode {obj!r} into {t!r}"
    raise NotImplementedError(msg)


class SeedsChart(msgspec.Struct):
    difficulty: Difficulty
    level: str
    const: float | None
    maxcombo: int
    tap: int
    hold: int
    slide: int
    air: int
    flick: int
    charter: str | None
    version: ChunithmVersion | None
    available: bool
    tachi_chart_id: str | None
    sdvxin: SeedsSdvxin | None


class SeedsSong(msgspec.Struct):
    id: int
    chunirec_id: str | None
    title: str
    wikiwiki_title: str | None
    chunithm_catcode: Genre
    genre: Literal[
        "POPS & ANIME",
        "niconico",
        "東方Project",
        "ORIGINAL",
        "VARIETY",
        "イロドリミドリ",
        "ゲキマイ",
        "WORLD'S END",
    ]
    artist: str
    version: ChunithmVersion
    release: str | None
    bpm: float | None
    min_bpm: float | None
    max_bpm: float | None
    jacket: str | None
    available: bool
    removed: bool
    is_hidden_on_chuninet: bool
    aliases: list[str]
    charts: list[SeedsChart]
    jackets: list[str]

    def __post_init__(self):
        if self.chunithm_catcode.value == Genre.all.value:
            msg = f"Cannot have a song with category code {Genre.all.value}"
            raise ValueError(msg)

        if self.genre != "WORLD'S END" and self.genre != str(self.chunithm_catcode):
            msg = f"Genre name does not agree with category code: genre={self.genre}, catcode={self.chunithm_catcode}"
            raise ValueError(msg)

        deduped = {c.difficulty for c in self.charts}

        if len(deduped) != len(self.charts):
            msg = "A song can only have one chart of each difficulty."
            raise ValueError(msg)


class ChartIdentifier(msgspec.Struct):
    song_id: int
    difficulty: Difficulty


class SeedsCourseTrack(msgspec.Struct):
    level: str | msgspec.UnsetType = msgspec.UNSET
    charts: list[ChartIdentifier] | msgspec.UnsetType = msgspec.UNSET

    def __post_init__(self):
        if self.level is not msgspec.UNSET and self.charts is not msgspec.UNSET:
            msg = "Only `level` or `charts` can be specified, not both."
            raise ValueError(msg)

        if self.charts is not msgspec.UNSET and len(self.charts) == 0:
            msg = "Chart list is empty."
            raise ValueError(msg)


class SeedsCourse(msgspec.Struct):
    id: int
    cls: Literal["i", "ii", "iii", "iv", "v", "infinite", "extra"]
    name: str
    version: str
    is_duplicate_track_allowed: bool
    life: int
    recovery_life: int
    clear_life: int
    damage_miss: int
    damage_attack: int
    damage_justice: int
    damage_jcrit: int
    tracks: list[SeedsCourseTrack]


class SeedsLinkedGateCondition(msgspec.Struct):
    level: LinkLevel
    region: Literal["jp", "intl"]
    difficulty: Difficulty
    life: int
    recovery_life: int
    damage_miss: int
    damage_attack: int
    damage_justice: int
    start_date: datetime
    end_date: datetime | None


class SeedsLinkedGate(msgspec.Struct):
    id: int
    name: str
    color: str
    song_id: int
    available: bool
    open_condition: str
    unlock_condition: str
    conditions: list[SeedsLinkedGateCondition]


class SeedsRepository:
    def __init__(self, logger: BoundLogger, base_dir: Path, *, is_local: bool = True):
        self.logger = logger
        self.base_dir = base_dir
        self.is_local = is_local

    def read[T: object](self, collection: str, typ: type[T]) -> T:
        with (self.base_dir / collection).with_suffix(".json").open("rb") as f:
            return msgspec.json.decode(f.read(), type=typ, dec_hook=msgspec_dec_hook)

    def read_raw(self, collection: str) -> Any:
        with (self.base_dir / collection).with_suffix(".json").open("rb") as f:
            return msgspec.json.decode(f.read())

    def write(self, collection: str, data: Any):
        with (self.base_dir / collection).with_suffix(".json").open("w") as f:
            json.dump(data, f, cls=SeedsJSONEncoder, indent=4, ensure_ascii=False)

    def authenticate_git(
        self, username: str, email: str, origin_url: str | None = None
    ):
        if self.is_local:
            return

        subprocess.check_call(
            ["git", "config", "user.name", username], cwd=self.base_dir
        )
        subprocess.check_call(["git", "config", "user.email", email], cwd=self.base_dir)

        if origin_url is not None:
            subprocess.check_call(
                ["git", "remote", "set-url", "origin", origin_url], cwd=self.base_dir
            )

    def commit_and_push_changes(self, message: str):
        if self.is_local:
            return

        stdout = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=self.base_dir
        )

        if not stdout:
            self.logger.info("No changes, not committing anything back.")
            return

        self.logger.info("Changes detected.")

        subprocess.check_call(["git", "add", "."], cwd=self.base_dir)
        stdout = subprocess.check_output(
            ["git", "commit", "-am", f"automated: {message}"], cwd=self.base_dir
        )
        subprocess.check_call(["git", "push"], cwd=self.base_dir)

        self.logger.info("Committed and pushed", message=stdout)

    def close(self):
        if not self.is_local:
            try:
                base_dir = subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"], cwd=self.base_dir
                ).strip()
            except subprocess.CalledProcessError:
                base_dir = self.base_dir

            shutil.rmtree(base_dir)


def pull_seeds_repository(
    logger: BoundLogger, seeds: LocalSeedsConfig | GitSeedsConfig
):
    if isinstance(seeds, LocalSeedsConfig):
        logger.info("opening local seeds repository", config=seeds.path)

        return SeedsRepository(logger, seeds.path, is_local=True)

    seeds_dir = tempfile.mkdtemp(prefix="chuni-penguin-seeds-")

    logger.info("pulling remote seeds directory", destination=seeds_dir, url=seeds.url)

    try:  # noqa: SIM105
        shutil.rmtree(seeds_dir)
    except FileNotFoundError:
        pass

    if seeds.branch is not msgspec.UNSET:
        output = subprocess.check_output(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--sparse",
                seeds.url,
                "-b",
                seeds.branch,
                seeds_dir,
            ]
        )
    else:
        output = subprocess.check_output(
            ["git", "clone", "--filter=blob:none", "--sparse", seeds.url, seeds_dir]
        )

    if output:
        raise Exception(output)  # noqa: TRY002

    subprocess.check_call(
        ["git", "sparse-checkout", "set", "--cone", "--sparse-index"], cwd=seeds_dir
    )
    output = subprocess.check_output(
        ["git", "sparse-checkout", "add", "chuni_penguin/database/seeds"], cwd=seeds_dir
    )

    if output:
        raise Exception(output)  # noqa: TRY002

    return SeedsRepository(
        logger, Path(seeds_dir) / "chuni_penguin" / "database" / "seeds", is_local=False
    )


async def dump_seeds(
    logger: BoundLogger,
    async_session: async_sessionmaker[AsyncSession],
    seeds_repo: SeedsRepository,
):
    async with async_session() as session:
        result = await session.execute(
            select(Song)
            .outerjoin(Alias, (Song.id == Alias.song_id) & (Alias.guild_id == 0))
            .options(joinedload(Song.charts).joinedload(Chart.sdvxin_chart_view))
            .options(contains_eager(Song.aliases))
            .options(joinedload(Song.jackets))
            .order_by(Song.id)
        )
        songs = []

        for row in result.scalars().unique():
            song = {c.name: getattr(row, c.name) for c in Song.__table__.columns}
            song["aliases"] = [arow.alias for arow in row.aliases]
            song["charts"] = []

            for crow in row.charts:
                chart = {
                    c.name: getattr(crow, c.name)
                    for c in Chart.__table__.columns
                    if c.name not in ("id", "song_id")
                }
                chart["sdvxin"] = (
                    {
                        "id": crow.sdvxin_chart_view.id,
                        "end_index": crow.sdvxin_chart_view.end_index,
                    }
                    if crow.sdvxin_chart_view is not None
                    else None
                )

                song["charts"].append(chart)

            song["jackets"] = [
                sjrow.jacket_url
                for sjrow in row.jackets
                if config.web.base_url is None
                or config.web.base_url not in sjrow.jacket_url
                or sjrow.jacket_url.split("/")[-1].split(".")[0].isdigit()
            ]

            songs.append(song)

        seeds_repo.write("songs", songs)
        logger.info("Written songs to database seeds", count=len(songs))
        del songs

        result = await session.execute(
            select(Course)
            .options(joinedload(Course.tracks).joinedload(CourseTrack.charts))
            .order_by(Course.id)
        )
        courses = []

        for row in result.scalars().unique():
            course = {c.name: getattr(row, c.name) for c in Course.__table__.columns}
            course["tracks"] = []

            trows = list(row.tracks.values())
            trows.sort(key=lambda t: t.track)

            for trow in trows:
                if trow.level is not None:
                    course["tracks"].append(
                        {
                            "level": trow.level,
                        }
                    )
                else:
                    course["tracks"].append(
                        {
                            "charts": [
                                {"song_id": crow.song_id, "difficulty": crow.difficulty}
                                for crow in trow.charts
                            ],
                        }
                    )

            courses.append(course)

        seeds_repo.write("courses", courses)
        logger.info("Written courses to database seeds", count=len(courses))
        del courses

        result = await session.execute(
            select(LinkedGate).options(joinedload(LinkedGate.conditions))
        )
        linked_gates = []

        for row in result.scalars().unique():
            linked_gate = {
                c.name: getattr(row, c.name) for c in LinkedGate.__table__.columns
            }
            linked_gate["conditions"] = [
                {
                    c.name: getattr(crow, c.name)
                    for c in LinkedGateCondition.__table__.columns
                    if c.name != "linked_gate_id"
                }
                for crow in row.conditions
            ]

            linked_gate["conditions"].sort(
                key=lambda c: (c["region"], c["level"]), reverse=True
            )

            linked_gates.append(linked_gate)

        seeds_repo.write("linked-gates", linked_gates)
        logger.info("Written Linked GATEs to database seeds", count=len(linked_gates))
        del linked_gates

    await sort_seeds(logger, seeds_repo)


async def delete_not_in_multiple_columns(
    connection: AsyncConnection,
    session: AsyncSession,
    table: "_DMLTableArgument",
    metadata: MetaData,
    columns: list[Column],
    values: list[dict[str, Any]],
):
    column_names = [c.name for c in columns]

    if hasattr(table, "__table__"):
        table = table.__table__  # pyright: ignore[reportAttributeAccessIssue]

    temp = Table(
        "temp_seeds_"
        + "".join(random.choice(string.ascii_lowercase) for _ in range(8)),
        metadata,
        *columns,
        PrimaryKeyConstraint(*column_names),
        prefixes=["TEMPORARY"],
    )

    await connection.run_sync(metadata.create_all, [temp])
    await session.execute(insert(temp), values)
    await session.execute(
        delete(table).where(
            ~exists().where(
                reduce(
                    operator.and_,
                    [
                        getattr(table.c, col) == getattr(temp.c, col)  # pyright: ignore[reportAttributeAccessIssue]
                        for col in column_names
                    ],
                    true(),
                )
            )
        )
    )

    await connection.run_sync(metadata.drop_all, [temp])


async def load_seeds(
    logger: BoundLogger, engine: AsyncEngine, seeds_repo: SeedsRepository
):
    async with (
        engine.begin() as connection,
        AsyncSession(connection, expire_on_commit=False) as session,
        session.begin(),
    ):
        logger.info("song, charts, sdvx.in chart view, jackets, aliases")

        songs = seeds_repo.read("songs", list[SeedsSong])

        # Remove songs that are not part of seeds
        query = delete(Song).where(Song.id.not_in([s.id for s in songs]))
        await session.execute(query)

        # Upsert songs
        query = insert(Song)
        query = query.on_conflict_do_update(
            index_elements=[Song.id],
            set_={
                c.name: getattr(query.excluded, c.name) for c in Song.__table__.columns
            },
        )

        await session.execute(
            query,
            [
                {
                    "chunithm_catcode": song.chunithm_catcode.value,
                    **{
                        c.name: getattr(song, c.name)
                        for c in Song.__table__.columns
                        if c.name != "chunithm_catcode"
                    },
                }
                for song in songs
            ],
        )

        # Remove charts that are not part of seeds
        await delete_not_in_multiple_columns(
            connection,
            session,
            Chart,
            Chart.metadata,
            [
                Column("song_id", Integer(), nullable=False),
                Column("difficulty", String(), nullable=False),
            ],
            [
                {"song_id": song.id, "difficulty": chart.difficulty.short()}
                for song in songs
                for chart in song.charts
            ],
        )

        # Upsert charts
        query = insert(Chart)
        query = query.on_conflict_do_update(
            index_elements=[Chart.song_id, Chart.difficulty],
            set_={
                c.name: getattr(query.excluded, c.name)
                for c in Chart.__table__.columns
                if c.name not in ("id", "song_id", "difficulty")
            },
        )
        await session.execute(
            query,
            [
                {
                    "song_id": song.id,
                    "difficulty": chart.difficulty.short(),
                    **{
                        c.name: getattr(chart, c.name)
                        for c in Chart.__table__.columns
                        if c.name not in ("id", "song_id", "difficulty")
                    },
                }
                for song in songs
                for chart in song.charts
            ],
        )

        # Remove sdvx.in chart views that are not part of seeds
        await delete_not_in_multiple_columns(
            connection,
            session,
            SdvxinChartView,
            SdvxinChartView.metadata,
            [
                Column("song_id", Integer(), nullable=False),
                Column("difficulty", String(), nullable=False),
            ],
            [
                {"song_id": song.id, "difficulty": chart.difficulty.short()}
                for song in songs
                for chart in song.charts
                if chart.sdvxin is not None
            ],
        )

        # Upsert sdvx.in chart views
        query = insert(SdvxinChartView)
        query = query.on_conflict_do_update(
            index_elements=[SdvxinChartView.song_id, SdvxinChartView.difficulty],
            set_={"id": query.excluded.id, "end_index": query.excluded.end_index},
        )
        await session.execute(
            query,
            [
                {
                    "id": chart.sdvxin.id,
                    "song_id": song.id,
                    "difficulty": chart.difficulty.short(),
                    "end_index": chart.sdvxin.end_index,
                }
                for song in songs
                for chart in song.charts
                if chart.sdvxin is not None
            ],
        )

        # Remove jacket URLs that are not part of seeds
        await session.execute(
            delete(SongJacket).where(
                SongJacket.jacket_url.not_in([j for s in songs for j in s.jackets])
            )
        )

        # Upsert jackets
        query = insert(SongJacket)
        query = query.on_conflict_do_update(
            index_elements=[SongJacket.jacket_url],
            set_={"song_id": query.excluded.song_id},
        )
        await session.execute(
            query,
            [{"song_id": s.id, "jacket_url": j} for s in songs for j in s.jackets],
        )

        # Update charts, aliases and jackets
        query = (
            select(Song)
            .outerjoin(Alias, (Song.id == Alias.song_id) & (Alias.guild_id == 0))
            .options(contains_eager(Song.aliases))
        )
        result = await session.execute(query)
        songs_by_id = {s.id: s for s in songs}

        for row in result.scalars().unique():
            song = songs_by_id[row.id]

            # ==== Aliases ====
            existing_aliases = {a.alias.lower() for a in row.aliases}
            seeds_aliases = {a.lower() for a in song.aliases}

            for a in song.aliases:
                if a.lower() not in existing_aliases:
                    session.add(
                        Alias(
                            alias=a,
                            guild_id=0,
                            owner_id=None,
                            song_id=row.id,
                            uses=0,
                        )
                    )

            for a in row.aliases:
                if a.guild_id == 0 and a.alias.lower() not in seeds_aliases:
                    await session.delete(a)

        logger.info("updated", count=len(songs))
        del songs_by_id
        del songs

        logger.info("courses")
        courses = seeds_repo.read("courses", list[SeedsCourse])

        # Delete courses that are not part of seeds
        query = delete(Course).where(Course.id.not_in([c.id for c in courses]))
        result = await session.execute(query)

        # Upsert courses
        query = insert(Course)
        query = query.on_conflict_do_update(
            index_elements=[Course.id],
            set_={
                c.name: getattr(query.excluded, c.name)
                for c in Course.__table__.columns
            },
        )

        await session.execute(
            query,
            [
                {
                    c.name: (
                        getattr(course, c.name)
                        if c.name != "cls"
                        else getattr(CourseClass, course.cls)
                    )
                    for c in Course.__table__.columns
                }
                for course in courses
            ],
        )

        # Delete course tracks that are not part of seeds
        await delete_not_in_multiple_columns(
            connection,
            session,
            CourseTrack,
            CourseTrack.metadata,
            [
                Column("course_id", Integer(), nullable=False),
                Column("track", Integer(), nullable=False),
            ],
            [
                {
                    "course_id": course.id,
                    "track": track_no + 1,
                }
                for course in courses
                for track_no, _ in enumerate(course.tracks)
            ],
        )

        # Upsert course tracks
        query = insert(CourseTrack)
        query = query.on_conflict_do_update(
            index_elements=[CourseTrack.course_id, CourseTrack.track],
            set_={"level": query.excluded.level},
        )

        await session.execute(
            query,
            [
                {
                    "course_id": course.id,
                    "track": track_no + 1,
                    "level": track.level if track.level is not msgspec.UNSET else None,
                }
                for course in courses
                for track_no, track in enumerate(course.tracks)
            ],
        )

        # Delete course track charts that are not part of seeds
        ctcs = [
            {
                "course_id": course.id,
                "track": track_no + 1,
                "song_id": chart.song_id,
                "difficulty": chart.difficulty.short(),
            }
            for course in courses
            for track_no, track in enumerate(course.tracks)
            if track.charts is not msgspec.UNSET
            for chart in track.charts
        ]

        await delete_not_in_multiple_columns(
            connection,
            session,
            course_track_charts,
            course_track_charts.metadata,
            [
                Column("course_id", Integer(), nullable=False),
                Column("track", Integer(), nullable=False),
                Column("song_id", Integer(), nullable=False),
                Column("difficulty", Integer(), nullable=False),
            ],
            ctcs,
        )

        # Upsert course track charts
        await session.execute(
            insert(course_track_charts).on_conflict_do_nothing(
                index_elements=[
                    course_track_charts.c.course_id,
                    course_track_charts.c.track,
                    course_track_charts.c.song_id,
                    course_track_charts.c.difficulty,
                ]
            ),
            ctcs,
        )
        logger.info("updated", count=len(courses))
        del courses

        logger.info("linked gates")
        linked_gates = seeds_repo.read("linked-gates", list[SeedsLinkedGate])

        # Remove gates that are not part of seeds
        query = delete(LinkedGate).where(
            LinkedGate.id.not_in([g.id for g in linked_gates])
        )
        await session.execute(query)

        # Upsert gates
        query = insert(LinkedGate)
        query = query.on_conflict_do_update(
            index_elements=[LinkedGate.id],
            set_={
                c.name: getattr(query.excluded, c.name)
                for c in LinkedGate.__table__.columns
                if c.name != "id"
            },
        )
        await session.execute(
            query,
            [
                {c.name: getattr(g, c.name) for c in LinkedGate.__table__.columns}
                for g in linked_gates
            ],
        )

        # Remove link levels that are not part of seeds
        await delete_not_in_multiple_columns(
            connection,
            session,
            LinkedGateCondition,
            LinkedGateCondition.metadata,
            [
                Column("linked_gate_id", Integer(), nullable=False),
                Column("level", Integer(), nullable=False),
                Column("region", String(), nullable=False),
            ],
            [
                {"linked_gate_id": g.id, "level": c.level.value, "region": c.region}
                for g in linked_gates
                for c in g.conditions
            ],
        )

        # Upsert linked gate conditions
        query = insert(LinkedGateCondition)
        query = query.on_conflict_do_update(
            index_elements=[
                LinkedGateCondition.linked_gate_id,
                LinkedGateCondition.level,
                LinkedGateCondition.region,
            ],
            set_={
                c.name: getattr(query.excluded, c.name)
                for c in LinkedGateCondition.__table__.columns
                if c.name not in ("linked_gate_id", "level", "region")
            },
        )
        await session.execute(
            query,
            [
                {
                    "linked_gate_id": gate.id,
                    "level": condition.level.value,
                    "region": condition.region,
                    "difficulty": condition.difficulty.short(),
                    "life": condition.life,
                    "recovery_life": condition.recovery_life,
                    "damage_miss": condition.damage_miss,
                    "damage_attack": condition.damage_attack,
                    "damage_justice": condition.damage_justice,
                    "start_date": condition.start_date,
                    "end_date": condition.end_date,
                }
                for gate in linked_gates
                for condition in gate.conditions
            ],
        )
        logger.info("updated", count=len(linked_gates))
        del linked_gates


async def validate_seeds(logger: BoundLogger, seeds_repo: SeedsRepository):
    files = {
        "songs": list[SeedsSong],
        "courses": list[SeedsCourse],
        "linked-gates": list[SeedsLinkedGate],
    }

    failed = False

    for filename, type in files.items():
        try:
            _ = seeds_repo.read(filename, type)
        except msgspec.DecodeError as e:
            logger.exception("verification failed", exc_info=e, collection=filename)
            failed = True
        else:
            logger.info("OK", collection=filename)

    if failed:
        sys.exit(1)


async def sort_seeds(logger: BoundLogger, seeds_repo: SeedsRepository):
    songs = seeds_repo.read_raw("songs")
    songs.sort(key=lambda s: s["id"])

    for song in songs:
        song["charts"].sort(
            key=lambda c: ["BAS", "ADV", "EXP", "MAS", "ULT", "WE"].index(
                c["difficulty"]
            )
        )
        song["jackets"].sort()

    seeds_repo.write("songs", songs)

    courses = seeds_repo.read_raw("courses")
    courses.sort(key=lambda s: s["id"])

    for course in courses:
        with contextlib.suppress(KeyError):
            course["charts"].sort(
                key=lambda c: (
                    c["song_id"],
                    ["BAS", "ADV", "EXP", "MAS", "ULT", "WE"].index(c["difficulty"]),
                )
            )

    seeds_repo.write("courses", courses)

    linked_gates = seeds_repo.read_raw("linked-gates")
    linked_gates.sort(key=lambda s: s["id"])

    for linked_gate in linked_gates:
        linked_gate["conditions"].sort(
            key=lambda c: (c["region"], c["level"]), reverse=True
        )

    seeds_repo.write("linked-gates", linked_gates)


async def backsync_seeds(
    logger: BoundLogger,
    async_session: async_sessionmaker[AsyncSession],
    seeds_config: GitSeedsConfig,
    seeds_repo: SeedsRepository,
    git_auth_username: str | None = None,
    git_auth_password: str | None = None,
):
    git_username = (
        git_auth_username
        or config.credentials.git_auth_username
        or os.environ["GIT_USERNAME"]
    )
    git_password = (
        git_auth_password
        or config.credentials.git_auth_password
        or os.environ["GIT_PASSWORD"]
    )

    await dump_seeds(logger, async_session, seeds_repo)
    await sort_seeds(logger, seeds_repo)

    seeds_repo.authenticate_git(
        seeds_config.username,
        seeds_config.email,
        str(
            yarl.URL(seeds_config.url)
            .with_user(git_username)
            .with_password(git_password)
        ),
    )
    seeds_repo.commit_and_push_changes(
        f"backsync database {datetime.now(UTC).isoformat()}"
    )
