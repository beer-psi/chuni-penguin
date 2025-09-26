import urllib.parse
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

import httpx
import msgspec

from chunithm_net.consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_PLAY_RATING,
    KEY_SONG_ID,
)
from chunithm_net.models.enums import ClearType, ComboType, Difficulty, Rank, SkillClass
from chunithm_net.models.player_data import PlayerData
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

KTChunithmNoteLamp = Literal[
    "NONE", "FULL COMBO", "ALL JUSTICE", "ALL JUSTICE CRITICAL"
]
KTChunithmClearLamp = Literal[
    "FAILED", "CLEAR", "HARD", "BRAVE", "ABSOLUTE", "CATASTROPHY"
]
KTChunithmDifficulty = Literal["BASIC", "ADVANCED", "EXPERT", "MASTER", "ULTIMA"]
KTChunithmClass = Literal[
    "DAN_I", "DAN_II", "DAN_III", "DAN_IV", "DAN_V", "DAN_INFINITE"
]


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
    note_lamp: KTChunithmNoteLamp
    clear_lamp: KTChunithmClearLamp
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
    difficulty: KTChunithmDifficulty
    is_primary: bool
    level: str
    level_num: float
    playtype: Literal["Single"]
    versions: list[str]
    data: KTChunithmChartData


class KTChunithmPersonalBestResponseBody(msgspec.Struct):
    pb: KTChunithmPersonalBest
    chart: KTChunithmChart


class KTChunithmPersonalBestsResponseBody(msgspec.Struct):
    pbs: list[KTChunithmPersonalBest]
    songs: list[KTChunithmSong]
    charts: list[KTChunithmChart]


class KTChunithmScoreResponseBody(msgspec.Struct):
    scores: list[KTChunithmScore]
    songs: list[KTChunithmSong]
    charts: list[KTChunithmChart]


class KTBatchManualChunithmMeta(msgspec.Struct):
    game: Literal["chunithm"] = "chunithm"
    playtype: Literal["Single"] = "Single"
    service: str = "site-importer"
    version: str | msgspec.UnsetType = msgspec.UNSET


class KTBatchManualChunithmScore(msgspec.Struct, rename="camel"):
    score: int
    note_lamp: KTChunithmNoteLamp
    clear_lamp: KTChunithmClearLamp
    match_type: Literal["inGameID", "songTitle", "tachiSongID"]
    identifier: str
    difficulty: KTChunithmDifficulty
    time_achieved: int | msgspec.UnsetType = msgspec.UNSET
    judgements: KTChunithmJudgements | msgspec.UnsetType = msgspec.UNSET
    optional: KTChunithmOptionalData | msgspec.UnsetType = msgspec.UNSET


class KTBatchManualChunithmClasses(msgspec.Struct):
    dan: KTChunithmClass | msgspec.UnsetType = msgspec.UNSET
    emblem: KTChunithmClass | msgspec.UnsetType = msgspec.UNSET


class KTBatchManualChunithm(msgspec.Struct):
    meta: KTBatchManualChunithmMeta = msgspec.field(
        default_factory=KTBatchManualChunithmMeta
    )
    scores: list[KTBatchManualChunithmScore] = msgspec.field(default_factory=list)
    classes: KTBatchManualChunithmClasses = msgspec.field(
        default_factory=KTBatchManualChunithmClasses
    )


class KTBatchManualResponseBody(msgspec.Struct):
    url: str


class KTImportErrContent(msgspec.Struct, rename="camel"):
    type: str
    message: str


class KTImportDocument(msgspec.Struct, rename="camel"):
    score_ids: list[str] = msgspec.field(name="scoreIDs")
    errors: list[KTImportErrContent]


class KTImportPollStatus(msgspec.Struct, rename="camel", tag_field="importStatus"):
    pass


class KTImportPollStatusOngoingProgress(msgspec.Struct):
    description: str
    value: int | msgspec.UnsetType = msgspec.UNSET


class KTImportPollStatusOngoing(KTImportPollStatus, tag="ongoing"):
    progress: KTImportPollStatusOngoingProgress | int


class KTImportPollStatusCompleted(KTImportPollStatus, tag="completed"):
    import_: KTImportDocument = msgspec.field(name="import")


class KTStatusResponseBody(msgspec.Struct, rename="camel"):
    server_time: int
    start_time: int
    version: str
    whoami: int | None
    permissions: list[str]


KTChunithmPersonalBestResponse = KTResponse[KTChunithmPersonalBestResponseBody]
KTChunithmPersonalBestsResponse = KTResponse[KTChunithmPersonalBestsResponseBody]
KTChunithmScoreResponse = KTResponse[KTChunithmScoreResponseBody]
KTBatchManualResponse = KTResponse[KTBatchManualResponseBody]
KTImportPollStatusResponse = KTResponse[
    KTImportPollStatusOngoing | KTImportPollStatusCompleted
]
KTStatusResponse = KTResponse[KTStatusResponseBody]


KT_CLEAR_LAMP_MAP: dict[KTChunithmClearLamp, ClearType] = {
    "CATASTROPHY": ClearType.CATASTROPHY,
    "ABSOLUTE": ClearType.ABSOLUTE,
    "BRAVE": ClearType.BRAVE,
    "HARD": ClearType.HARD,
    "CLEAR": ClearType.CLEAR,
    "FAILED": ClearType.FAILED,
}
KT_REVERSE_CLEAR_LAMP_MAP: dict[ClearType, KTChunithmClearLamp] = {
    v: k for k, v in KT_CLEAR_LAMP_MAP.items()
}

KT_NOTE_LAMP_MAP: dict[KTChunithmNoteLamp, ComboType] = {
    "ALL JUSTICE CRITICAL": ComboType.ALL_JUSTICE_CRITICAL,
    "ALL JUSTICE": ComboType.ALL_JUSTICE,
    "FULL COMBO": ComboType.FULL_COMBO,
    "NONE": ComboType.NONE,
}
KT_REVERSE_NOTE_LAMP_MAP: dict[ComboType, KTChunithmNoteLamp] = {
    v: k for k, v in KT_NOTE_LAMP_MAP.items()
}


def convert_kt_to_record(
    score: KTChunithmScore | KTChunithmPersonalBest,
    song_title: str,
    chart: KTChunithmChart,
):
    judgements = score.score_data.judgements
    record = Record(
        title=song_title,
        difficulty=getattr(Difficulty, chart.difficulty),
        score=score.score_data.score,
        rank=getattr(Rank, score.score_data.grade.replace("+", "p")),
        clear_lamp=KT_CLEAR_LAMP_MAP.get(score.score_data.clear_lamp, ClearType.FAILED),
        combo_lamp=KT_NOTE_LAMP_MAP.get(score.score_data.note_lamp, ComboType.NONE),
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


def convert_kt_pbs_to_records(
    raw_body: Any | KTChunithmPersonalBestsResponseBody,
) -> list[Record]:
    if isinstance(raw_body, KTChunithmPersonalBestsResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmPersonalBestsResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        convert_kt_to_record(
            pb, songs_by_id[pb.song_id].title, charts_by_id[pb.chart_id]
        )
        for pb in body.pbs
    ]


def convert_kt_scores_to_records(
    raw_body: Any | KTChunithmScoreResponseBody,
) -> list[Record]:
    if isinstance(raw_body, KTChunithmScoreResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmScoreResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        convert_kt_to_record(
            score, songs_by_id[score.song_id].title, charts_by_id[score.chart_id]
        )
        for score in body.scores
    ]


def _to_tachi_class(cls: SkillClass) -> KTChunithmClass:
    mapping: dict[SkillClass, KTChunithmClass] = {
        SkillClass.I: "DAN_I",
        SkillClass.II: "DAN_II",
        SkillClass.III: "DAN_III",
        SkillClass.IV: "DAN_IV",
        SkillClass.V: "DAN_V",
        SkillClass.INFINITE: "DAN_INFINITE",
    }

    return mapping[cls]


def convert_to_kt_batch_manual(
    profile: PlayerData, scores: list[DetailedRecentRecord | RecentRecord | Record]
):
    batch_manual = KTBatchManualChunithm()

    if profile.medal is not None:
        batch_manual.classes.dan = _to_tachi_class(profile.medal)
    if profile.emblem is not None:
        batch_manual.classes.emblem = _to_tachi_class(profile.emblem)

    for score in scores:
        if score.difficulty == Difficulty.WORLDS_END:
            continue

        if (song_id := score.extras.get(KEY_SONG_ID)) is None:
            continue

        tachi_score = KTBatchManualChunithmScore(
            score=score.score,
            note_lamp=KT_REVERSE_NOTE_LAMP_MAP.get(score.combo_lamp, "NONE"),
            clear_lamp=KT_REVERSE_CLEAR_LAMP_MAP.get(score.clear_lamp, "FAILED"),
            match_type="inGameID",
            identifier=str(song_id),
            difficulty=str(score.difficulty),  # pyright: ignore[reportArgumentType]
        )

        if isinstance(score, RecentRecord):
            tachi_score.time_achieved = int(score.date.timestamp() * 1000)

        if isinstance(score, DetailedRecentRecord):
            tachi_score.judgements = KTChunithmJudgements(
                jcrit=score.judgements.jcrit,
                justice=score.judgements.justice,
                attack=score.judgements.attack,
                miss=score.judgements.miss,
            )
            tachi_score.optional = KTChunithmOptionalData(max_combo=score.max_combo)

        batch_manual.scores.append(tachi_score)

    return batch_manual


class KamaitachiClient:
    def __init__(
        self, client: httpx.AsyncClient, base_url: str = "https://kamai.tachi.ac"
    ) -> None:
        self._client = client
        self.base_url = base_url

    async def get(self, url: str) -> httpx.Response:
        return await self._client.get(url)

    async def chunithm_profile(self) -> httpx.Response:
        return await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single"
        )

    async def pb_for_chart(self, chart_id: str) -> KTChunithmPersonalBestResponse:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single/pbs/{chart_id}"
        )

        return msgspec.json.decode(resp.content, type=KTChunithmPersonalBestResponse)

    async def pbs(self) -> KTChunithmPersonalBestsResponse:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single/pbs/all"
        )

        return msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

    async def best_pbs(
        self, algorithm: str = "rating"
    ) -> KTChunithmPersonalBestsResponse:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single/pbs/best?alg={urllib.parse.quote(algorithm)}"
        )

        return msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

    async def search_pbs(self, query: str) -> KTChunithmPersonalBestsResponse:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single/pbs?search={urllib.parse.quote(query)}"
        )

        return msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

    async def recent_scores(self) -> KTChunithmScoreResponse:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/users/me/games/chunithm/Single/scores/recent"
        )

        return msgspec.json.decode(resp.content, type=KTChunithmScoreResponse)
