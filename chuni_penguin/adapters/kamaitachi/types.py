import functools
from enum import Enum
from typing import Literal

import msgspec

from chuni_penguin.adapters.errors import NetworkError
from chuni_penguin.types import SkillClass

KTChunithmNoteLamp = Literal[
    "NONE", "FULL COMBO", "ALL JUSTICE", "ALL JUSTICE CRITICAL"
]
KTChunithmClearLamp = Literal[
    "FAILED", "CLEAR", "HARD", "BRAVE", "ABSOLUTE", "CATASTROPHY"
]
KTChunithmDifficulty = Literal["BASIC", "ADVANCED", "EXPERT", "MASTER", "ULTIMA"]


@functools.total_ordering
class KTChunithmClass(Enum):
    i = "DAN_I"
    ii = "DAN_II"
    iii = "DAN_III"
    iv = "DAN_IV"
    v = "DAN_V"
    infinite = "DAN_INFINITE"

    def __lt__(self, other: object):
        if not isinstance(other, KTChunithmClass):
            return NotImplemented

        members = list(KTChunithmClass)

        return members.index(self) < members.index(other)

    @classmethod
    def from_skill_class(cls, skill_class: SkillClass):
        if skill_class == SkillClass.i:
            return cls.i
        if skill_class == SkillClass.ii:
            return cls.ii
        if skill_class == SkillClass.iii:
            return cls.iii
        if skill_class == SkillClass.iv:
            return cls.iv
        if skill_class == SkillClass.v:
            return cls.v
        if skill_class == SkillClass.infinite:
            return cls.infinite

        msg = f"Invalid skill class: {skill_class}"
        raise ValueError(msg)


class KamaitachiError(NetworkError):
    pass


class Empty(msgspec.Struct):
    pass


class KTResponse[T](msgspec.Struct):
    success: bool
    description: str
    body: T | None = None


class KTUserProfile(msgspec.Struct, rename="camel"):
    id: int
    username: str
    custom_banner_location: str | None
    custom_pfp_location: str | None


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


class KTChunithmChartResolveResponseBody(msgspec.Struct):
    chart: KTChunithmChart
    song: KTChunithmSong


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


class KTSessionInfoReturn(msgspec.Struct, rename="camel"):
    session_id: str = msgspec.field(name="sessionID")
    type: Literal["Appended", "Created"]


class KTImportDocument(msgspec.Struct, rename="camel"):
    user_id: int = msgspec.field(name="userID")
    time_finished: int
    score_ids: list[str] = msgspec.field(name="scoreIDs")
    game: str
    errors: list[KTImportErrContent]
    created_sessions: list[KTSessionInfoReturn]


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


class KTChunithmRatings(msgspec.Struct, rename="camel"):
    naive_rating: float


class KTChunithmClasses(msgspec.Struct, rename="camel"):
    colour: str | msgspec.UnsetType = msgspec.UNSET
    dan: str | msgspec.UnsetType = msgspec.UNSET
    emblem: str | msgspec.UnsetType = msgspec.UNSET


class KTChunithmGameStats(msgspec.Struct, rename="camel"):
    game: str
    playtype: str
    userID: int
    ratings: KTChunithmRatings
    classes: KTChunithmClasses


class KTChunithmUserProfile(msgspec.Struct, rename="camel"):
    game_stats: KTChunithmGameStats
    most_recent_score: KTChunithmScore | None
    total_scores: int
    playtime: int


class KTChunithmLeaderboard(msgspec.Struct, rename="camel"):
    pbs: list[KTChunithmPersonalBest]
    users: list[KTUserProfile]


KTChunithmPersonalBestResponse = KTResponse[KTChunithmPersonalBestResponseBody]
KTChunithmPersonalBestsResponse = KTResponse[KTChunithmPersonalBestsResponseBody]
KTChunithmScoreResponse = KTResponse[KTChunithmScoreResponseBody]
KTBatchManualResponse = KTResponse[KTBatchManualResponseBody]
KTImportPollStatusResponse = KTResponse[
    KTImportPollStatusOngoing | KTImportPollStatusCompleted
]
KTStatusResponse = KTResponse[KTStatusResponseBody]
