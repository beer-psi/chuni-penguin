from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from discord.utils import MISSING
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from chuni_penguin.calculation import (
    calculate_ongeki_platinum_rating,
    calculate_ongeki_rating,
    calculate_overpower_base,
    calculate_overpower_max,
    calculate_play_overpower,
    calculate_rating,
)
from chuni_penguin.constants import CURRENT_CHUNITHM_VERSION
from chuni_penguin.database import Song
from chuni_penguin.logging import logger
from chuni_penguin.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Genre,
    Judgements,
    PersonalBest,
    RatingBreakdown,
    RatingFrame,
    RatingFrameType,
    RatingType,
    Score,
)
from chuni_penguin.utils import floor_to_ndp, get_jacket_url

if TYPE_CHECKING:
    from chuni_penguin.cogs.database import DatabaseCog


async def hydrate_records[T: Score](
    database: "DatabaseCog", records: Sequence[T]
) -> list[T]:
    song_ids = set()
    jackets = set()
    titles = set()

    for record in records:
        song_id = record.song.id

        if song_id is not MISSING:
            if song_id == 723:
                # sega revived an old song under a different ID for whatever reason, and people have scores on both of them.
                # we only have scores on ID 808 though. this is quite a bodge.
                record.song.id = song_id = 808

            song_ids.add(song_id)
        elif record.song.jacket_url is not None:
            jackets.add(record.song.jacket_url.split("/")[-1])
        else:
            titles.add(record.song.title)

    async with database.read_sessionmaker() as session:
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
        song_lookup[song.title] = song

        if song.jacket is not None:
            song_lookup[song.jacket] = song

    hydrated_records = []

    for record in records[:]:
        song_id = record.song.id

        if song_id is not MISSING:
            song = song_lookup.get(song_id)
        elif record.song.jacket_url is not None:
            song = song_lookup.get(record.song.jacket_url.split("/")[-1])
        else:
            song = song_lookup.get(record.song.title)

        if song is None:
            await logger.awarning(
                "Missing song data",
                tag="missing_song_data",
                title=record.song.title,
            )
            hydrated_records.append(record)
            continue

        if song_id is MISSING:
            record.song.id = song.id

        if record.song.version is None:
            record.song.version = song.version

        if not record.song.title:
            record.song.title = song.title

        if record.song.jacket_url is None:
            record.song.jacket_url = get_jacket_url(song)

        chart = next(
            (c for c in song.charts if c.difficulty == record.chart.difficulty.short()),
            None,
        )

        if chart is None:
            await logger.awarning(
                "Missing chart data",
                tag="missing_chart_data",
                song_id=song.id,
                difficulty=record.chart.difficulty,
            )
            hydrated_records.append(record)
            continue

        if record.chart.level is None:
            record.chart.level = chart.level

        if (internal_level := record.chart.internal_level) is None:
            if chart.const is None:
                try:
                    internal_level = record.chart.internal_level = float(
                        chart.level.replace("+", ".5")
                    )
                except ValueError:
                    internal_level = record.chart.internal_level = 0
            else:
                internal_level = record.chart.internal_level = chart.const

        if record.rating is None:
            record.rating = calculate_rating(record.score, internal_level)

        if record.ongeki_rating is None:
            record.ongeki_rating = calculate_ongeki_rating(
                record.score, internal_level, record.combo_lamp
            )

        if record.ongeki_platinum_rating is None:
            record.ongeki_platinum_rating = calculate_ongeki_platinum_rating(
                record.score, internal_level
            )

        if record.overpower is None:
            record.overpower = calculate_play_overpower(
                calculate_overpower_base(record.score, internal_level),
                record.combo_lamp,
            )

        if record.chart.max_overpower is None:
            record.chart.max_overpower = calculate_overpower_max(internal_level)

        if record.song.genre is None:
            record.song.genre = Genre(song.chunithm_catcode)

        # Hydrate maxcombo and judgement data when possible.
        if chart.maxcombo is not None:
            if record.chart.max_combo is None:
                record.chart.max_combo = chart.maxcombo

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


async def process_record[T: Score](
    database: "DatabaseCog", discord_id: int, network: str, record: T
) -> T:
    return (await process_records(database, discord_id, network, [record]))[0]


async def process_records[T: Score](
    database: "DatabaseCog", discord_id: int, network: str, records: Sequence[T]
) -> list[T]:
    hydrated_records = await hydrate_records(database, records)
    db_records = await database.personal_bests.upsert_personal_bests(
        discord_id,
        network,
        hydrated_records,  # pyright: ignore[reportArgumentType]
    )
    db_records_by_chart = {(r.song_id, r.difficulty): r for r in db_records}

    # Annotate hydrated records with PB stored in database when applicable.
    # The returned DB records are better than or equal to the records we're trying
    # to hydrate, since they're personal bests.
    for record in hydrated_records:
        try:
            db_record = db_records_by_chart[
                (record.song.id, record.chart.difficulty.short())
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


def calculate_ongeki_rating_breakdown(
    rating_type: Literal[RatingType.ongeki, RatingType.ongeki_naive],
    pbs: list[PersonalBest],
) -> RatingBreakdown:
    platinum_pbs = [
        pb
        for pb in pbs
        if pb.ongeki_platinum_rating is not None and pb.ongeki_platinum_rating > 0
    ]

    pbs.sort(
        key=lambda pb: (
            pb.ongeki_rating,
            pb.score,
            pb.combo_lamp,
            pb.chart.internal_level,
        ),
        reverse=True,
    )
    platinum_pbs.sort(
        key=lambda pb: (
            pb.ongeki_platinum_rating,
            pb.score,
            pb.combo_lamp,
            pb.chart.internal_level,
        ),
        reverse=True,
    )

    if rating_type == RatingType.ongeki:
        best = []
        new = []

        for pb in pbs:
            if pb.song.version == CURRENT_CHUNITHM_VERSION:
                if len(new) < 10:
                    new.append(pb)
            elif len(best) < 50:
                best.append(pb)

            if len(best) == 50 and len(new) == 10:
                break

        rating = floor_to_ndp(
            (
                sum(
                    [r.ongeki_rating or Decimal(0) for r in best],
                    start=Decimal(0),
                )
                / 50
            )
            + (
                sum(
                    [r.ongeki_rating or Decimal(0) for r in new],
                    start=Decimal(0),
                )
                / 10
                / 5
            )
            + (
                sum(
                    [r.ongeki_platinum_rating or Decimal(0) for r in platinum_pbs],
                    start=Decimal(0),
                )
                / 50
            ),
            3,
        )

        return RatingBreakdown(
            rating=rating,
            frames={
                RatingFrameType.best: RatingFrame(
                    type=RatingFrameType.best,
                    num_scores=50,
                    scores=best,
                ),
                RatingFrameType.new: RatingFrame(
                    type=RatingFrameType.new,
                    num_scores=10,
                    scores=new,
                ),
                RatingFrameType.platinum: RatingFrame(
                    type=RatingFrameType.platinum,
                    num_scores=50,
                    scores=platinum_pbs[:50],
                ),
            },
        )

    if rating_type == RatingType.ongeki_naive:
        pbs = pbs[:60]
        platinum_pbs = platinum_pbs[:50]
        rating = floor_to_ndp(
            floor_to_ndp(
                sum(
                    [r.ongeki_rating or Decimal(0) for r in pbs],
                    start=Decimal(0),
                )
                / 60
                * Decimal("1.2"),
                3,
            )
            + (
                sum(
                    [r.ongeki_platinum_rating or Decimal(0) for r in platinum_pbs],
                    start=Decimal(0),
                )
                / 50
            ),
            3,
        )

        return RatingBreakdown(
            rating=rating,
            frames={
                RatingFrameType.best: RatingFrame(
                    type=RatingFrameType.best,
                    num_scores=60,
                    scores=pbs,
                ),
                RatingFrameType.platinum: RatingFrame(
                    type=RatingFrameType.platinum,
                    num_scores=50,
                    scores=platinum_pbs,
                ),
            },
        )

    msg = f"Unknown RatingType variant {rating_type!r}"
    raise RuntimeError(msg)
