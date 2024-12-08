from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

import msgspec

from chunithm_net.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_PLAY_RATING,
    KEY_SONG_ID,
)
from chunithm_net.models.enums import ClearType, ComboType, Difficulty, Rank
from chunithm_net.models.record import (
    DetailedRecentRecord,
    Judgements,
    NoteType,
    RecentRecord,
    Record,
    Skill,
)
from utils import floor_to_ndp

T = TypeVar("T", bound=msgspec.Struct)


class KTResponse(msgspec.Struct, Generic[T]):
    success: bool
    description: str
    body: T | None = None


class KTChunithmCalculatedData(msgspec.Struct, rename="camel"):
    rating: float


class KTRankingData(msgspec.Struct, rename="camel"):
    rank: int
    out_of: int
    rival_rank: int | None


class KTChunithmJudgements(msgspec.Struct, rename="camel"):
    jcrit: int | None = None
    justice: int | None = None
    attack: int | None = None
    miss: int | None = None


class KTChunithmOptionalData(msgspec.Struct, rename="camel"):
    max_combo: int | None = None


class KTChunithmScoreData(msgspec.Struct, rename="camel"):
    score: int
    lamp: Literal[
        "FAILED", "CLEAR", "FULL COMBO", "ALL JUSTICE", "ALL JUSTICE CRITICAL"
    ]
    judgements: KTChunithmJudgements
    optional: KTChunithmOptionalData
    grade: Literal[
        "SSS+",
        "SSS",
        "SS+",
        "SS",
        "S+",
        "S",
        "AAA",
        "AA",
        "A",
        "BBB",
        "BB",
        "B",
        "C",
        "D",
    ]


class KTChunithmPersonalBestComposition(msgspec.Struct, rename="camel"):
    name: str
    score_id: str = msgspec.field(name="scoreID")


class KTChunithmPersonalBest(msgspec.Struct, rename="camel"):
    user_id: int = msgspec.field(name="userID")
    game: Literal["chunithm"]
    playtype: Literal["Single"]

    song_id: int = msgspec.field(name="songID")
    chart_id: str = msgspec.field(name="chartID")

    score_data: KTChunithmScoreData
    calculated_data: KTChunithmCalculatedData
    composed_from: list[KTChunithmPersonalBestComposition]

    is_primary: bool
    highlight: bool
    ranking_data: KTRankingData
    time_achieved: int | None


class KTChunithmScore(msgspec.Struct, rename="camel"):
    score_id: str = msgspec.field(name="scoreID")

    user_id: int = msgspec.field(name="userID")
    game: Literal["chunithm"]
    playtype: Literal["Single"]

    song_id: int = msgspec.field(name="songID")
    chart_id: str = msgspec.field(name="chartID")

    import_type: str
    service: str

    score_data: KTChunithmScoreData
    calculated_data: KTChunithmCalculatedData

    is_primary: bool
    highlight: bool
    comment: str | None
    time_added: int
    time_achieved: int | None


class KTChunithmSongData(msgspec.Struct, rename="camel"):
    display_version: str
    genre: str


class KTChunithmSong(msgspec.Struct, rename="camel"):
    id: int
    title: str
    artist: str
    alt_titles: list[str]
    search_terms: list[str]
    data: KTChunithmSongData


class KTChunithmChartData(msgspec.Struct, rename="camel"):
    in_game_id: int = msgspec.field(name="inGameID")


class KTChunithmChart(msgspec.Struct, rename="camel"):
    chart_id: str = msgspec.field(name="chartID")
    song_id: int = msgspec.field(name="songID")
    difficulty: Literal["BASIC", "ADVANCED", "EXPERT", "MASTER", "ULTIMA"]
    is_primary: bool
    level: str
    level_num: float
    playtype: Literal["Single"]
    versions: list[str]
    data: KTChunithmChartData


class KTChunithmPersonalBestResponseBody(msgspec.Struct):
    pbs: list[KTChunithmPersonalBest]
    songs: list[KTChunithmSong]
    charts: list[KTChunithmChart]


class KTChunithmScoreResponseBody(msgspec.Struct):
    scores: list[KTChunithmScore]
    songs: list[KTChunithmSong]
    charts: list[KTChunithmChart]


KTChunithmPersonalBestResponse = KTResponse[KTChunithmPersonalBestResponseBody]
KTChunithmScoreResponse = KTResponse[KTChunithmScoreResponseBody]


def _convert_kt_to_record(
    score: KTChunithmScore | KTChunithmPersonalBest,
    song: KTChunithmSong,
    chart: KTChunithmChart,
):
    judgements = score.score_data.judgements
    record = Record(
        title=song.title,
        difficulty=getattr(Difficulty, chart.difficulty),
        score=score.score_data.score,
        rank=getattr(Rank, score.score_data.grade.replace("+", "p")),
        clear_lamp=(
            ClearType.CLEAR if score.score_data.lamp != "FAILED" else ClearType.FAILED
        ),
        combo_lamp=(
            ComboType.NONE
            if score.score_data.lamp in ("FAILED", "CLEAR")
            else getattr(ComboType, score.score_data.lamp.replace(" ", "_"))
        ),
    )
    record.extras[KEY_SONG_ID] = chart.data.in_game_id
    record.extras[KEY_LEVEL] = chart.level
    record.extras[KEY_INTERNAL_LEVEL] = chart.level_num
    record.extras[KEY_PLAY_RATING] = floor_to_ndp(
        Decimal(str(score.calculated_data.rating)), 2
    )

    if score.time_achieved:
        record = RecentRecord(
            track=-1,
            date=datetime.fromtimestamp(score.time_achieved / 1000, tz=UTC),
            new_record=False,
            **record.__dict__,
        )

    if (
        judgements.jcrit is not None
        and judgements.justice is not None
        and judgements.attack is not None
        and judgements.miss is not None
    ):
        kwargs = {
            "character": "",
            "skill": Skill(name="", grade=None),
            "skill_result": -1,
            "max_combo": score.score_data.optional.max_combo or -1,
            "judgements": Judgements(
                jcrit=judgements.jcrit,
                justice=judgements.justice,
                attack=judgements.attack,
                miss=judgements.miss,
            ),
            "note_type": NoteType(-1, -1, -1, -1, -1),
            **record.__dict__,
        }

        if "track" not in kwargs:
            kwargs["track"] = -1

        if "date" not in kwargs:
            kwargs["date"] = datetime.fromtimestamp(
                (score.time_achieved or 0) / 1000, tz=UTC
            )

        if "new_record" not in kwargs:
            kwargs["new_record"] = False

        record = DetailedRecentRecord(**kwargs)

    return record


def convert_kt_pbs_to_records(raw_body: Any) -> list[Record]:
    body = msgspec.convert(raw_body, KTChunithmPersonalBestResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        _convert_kt_to_record(pb, songs_by_id[pb.song_id], charts_by_id[pb.chart_id])
        for pb in body.pbs
    ]


def convert_kt_scores_to_records(raw_body: Any) -> list[Record]:
    body = msgspec.convert(raw_body, KTChunithmScoreResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        _convert_kt_to_record(
            score, songs_by_id[score.song_id], charts_by_id[score.chart_id]
        )
        for score in body.scores
    ]
