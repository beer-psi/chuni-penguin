import asyncio
import functools
import io
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from http.client import NOT_FOUND
from typing import Any, Generic, Literal, TypeVar

import httpx
import httpx_aiohttp
import magic
import msgspec

from chuni_penguin.config import config
from chuni_penguin.utils import floor_to_ndp

from ._hooks import raise_on_server_errors
from .base import Network
from .consts import (
    KEY_INTERNAL_LEVEL,
    KEY_LEVEL,
    KEY_PLAY_RATING,
    KEY_SONG_ID,
    KEY_SONG_VERSION,
)
from .errors import ChartNotFound, NetworkError, SongNotFound
from .types import (
    ClearLamp,
    ComboLamp,
    Difficulty,
    Judgements,
    Leaderboard,
    LeaderboardEntry,
    PersonalBest,
    Profile,
    Rank,
    RatingSystem,
    RecentScore,
    Score,
    SkillClass,
)

T = TypeVar("T", bound=msgspec.Struct)

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


class KTResponse(msgspec.Struct, Generic[T]):
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


KT_CLEAR_LAMP_MAP: dict[KTChunithmClearLamp, ClearLamp] = {
    "CATASTROPHY": ClearLamp.catastrophy,
    "ABSOLUTE": ClearLamp.absolute,
    "BRAVE": ClearLamp.brave,
    "HARD": ClearLamp.hard,
    "CLEAR": ClearLamp.clear,
    "FAILED": ClearLamp.failed,
}
KT_REVERSE_CLEAR_LAMP_MAP: dict[ClearLamp, KTChunithmClearLamp] = {
    v: k for k, v in KT_CLEAR_LAMP_MAP.items()
}

KT_NOTE_LAMP_MAP: dict[KTChunithmNoteLamp, ComboLamp] = {
    "ALL JUSTICE CRITICAL": ComboLamp.all_justice_critical,
    "ALL JUSTICE": ComboLamp.all_justice,
    "FULL COMBO": ComboLamp.full_combo,
    "NONE": ComboLamp.none,
}
KT_REVERSE_NOTE_LAMP_MAP: dict[ComboLamp, KTChunithmNoteLamp] = {
    v: k for k, v in KT_NOTE_LAMP_MAP.items()
}


def convert_kt_to_score(
    score: KTChunithmScore | KTChunithmPersonalBest,
    song_title: str,
    chart: KTChunithmChart,
    song_version: str | None = None,
):
    judgements = score.score_data.judgements
    record = Score(
        title=song_title,
        difficulty=getattr(Difficulty, chart.difficulty.lower()),
        score=score.score_data.score,
        rank=getattr(Rank, score.score_data.grade.lower().replace("+", "p")),
        clear_lamp=KT_CLEAR_LAMP_MAP.get(score.score_data.clear_lamp, ClearLamp.failed),
        combo_lamp=KT_NOTE_LAMP_MAP.get(score.score_data.note_lamp, ComboLamp.none),
        max_combo=score.score_data.optional.max_combo,
    )
    record.extras[KEY_SONG_ID] = chart.data.in_game_id
    record.extras[KEY_LEVEL] = chart.level
    record.extras[KEY_INTERNAL_LEVEL] = chart.level_num
    record.extras[KEY_PLAY_RATING] = floor_to_ndp(
        Decimal(str(score.calculated_data.rating)), 2
    )

    if song_version is not None:
        if song_version not in ("CHUNITHM", "CHUNITHM PLUS"):
            song_version = song_version.removeprefix("CHUNITHM ")

        record.extras[KEY_SONG_VERSION] = song_version

    if score.time_achieved:
        record.achieved_at = datetime.fromtimestamp(score.time_achieved / 1000, tz=UTC)

    if (
        judgements.jcrit is not None
        and judgements.justice is not None
        and judgements.attack is not None
        and judgements.miss is not None
    ):
        record.judgements = Judgements(
            justice_critical=judgements.jcrit,
            justice=judgements.justice,
            attack=judgements.attack,
            miss=judgements.miss,
        )

    return record


def convert_kt_pbs_to_records(
    raw_body: Any | KTChunithmPersonalBestsResponseBody,
) -> list[PersonalBest]:
    if isinstance(raw_body, KTChunithmPersonalBestsResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmPersonalBestsResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        PersonalBest(
            **convert_kt_to_score(
                pb,
                songs_by_id[pb.song_id].title,
                charts_by_id[pb.chart_id],
                songs_by_id[pb.song_id].data.display_version,
            ).__dict__
        )
        for pb in body.pbs
    ]


def convert_kt_scores_to_records(
    raw_body: Any | KTChunithmScoreResponseBody,
) -> list[RecentScore]:
    if isinstance(raw_body, KTChunithmScoreResponseBody):
        body = raw_body
    else:
        body = msgspec.convert(raw_body, KTChunithmScoreResponseBody)

    songs_by_id = {s.id: s for s in body.songs}
    charts_by_id = {c.chart_id: c for c in body.charts}

    return [
        RecentScore(
            **convert_kt_to_score(
                score,
                songs_by_id[score.song_id].title,
                charts_by_id[score.chart_id],
                songs_by_id[score.song_id].data.display_version,
            ).__dict__
        )
        for score in body.scores
    ]


def convert_to_kt_batch_manual(profile: Profile, scores: Sequence[Score]):
    batch_manual = KTBatchManualChunithm()

    if profile.medal is not None:
        batch_manual.classes.dan = KTChunithmClass.from_skill_class(profile.medal)
    if profile.emblem is not None:
        batch_manual.classes.emblem = KTChunithmClass.from_skill_class(profile.emblem)

    for score in scores:
        if score.difficulty == Difficulty.worlds_end:
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

        if score.achieved_at is not None:
            tachi_score.time_achieved = int(score.achieved_at.timestamp() * 1000)

        if score.judgements is not None:
            tachi_score.judgements = KTChunithmJudgements(
                jcrit=score.judgements.justice_critical,
                justice=score.judgements.justice,
                attack=score.judgements.attack,
                miss=score.judgements.miss,
            )

        if score.max_combo is not None:
            tachi_score.optional = KTChunithmOptionalData(max_combo=score.max_combo)

        batch_manual.scores.append(tachi_score)

    return batch_manual


async def guess_mime_type(response: httpx.Response) -> str:
    data = io.BytesIO()

    async for chunk in response.aiter_bytes():
        if data.tell() == 0:
            # some simple and common formats can be checked first without
            # calling into libmagic
            fourcc = chunk[:4]

            if fourcc == b"GIF8":
                return "image/gif"

            if fourcc == b"\x89PNG":
                return "image/png"

            if fourcc[:3] == b"\xff\xd8\xff" and fourcc[3] in (0xDB, 0xE0, 0xE1, 0xEE):
                return "image/jpeg"

            if fourcc == b"RIFF" and fourcc[8:12] == b"WEBP":
                return "image/webp"

        data.write(chunk)

        if data.tell() >= 2048:
            break

    return magic.from_buffer(data.getvalue(), mime=True)


class Kamaitachi(Network):
    NAME = "Kamaitachi"
    ACCENT_COLOR = 0xCA1961

    DEFAULT_RATING_SYSTEM = "NaiveRating"

    SUPPORTS_PROFILE = True
    SUPPORTS_RECENT_SCORES = True
    SUPPORTS_BEST_RATINGS = True
    SUPPORTS_PERSONAL_BESTS = True
    SUPPORTS_PERSONAL_BESTS_ON_SONG = True
    SUPPORTS_CHART_LEADERBOARD = True

    def __init__(
        self, authentication: str, *, base_url: str = "https://kamai.tachi.ac"
    ):
        self._api_key = authentication
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {authentication}",
                "User-Agent": f"chuni-penguin (+https://github.com/beer-psi/chuni-penguin) Python/{sys.version_info[0]}.{sys.version_info[1]} httpx/{httpx.__version__}",
            },
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            event_hooks={"response": [raise_on_server_errors]},
            base_url=base_url,
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5),
        )

        # Functions to map a (songID, Difficulty) to a song ID for retrieving PBs
        self.get_kt_chart_id: Callable[[int, Difficulty], Awaitable[str | None]] = (
            self._get_kt_chart_id
        )
        self.get_kt_chart_ids: Callable[[int], Awaitable[list[str]]] = (
            self._get_kt_chart_ids
        )

        self._kt_charts: list[KTChunithmChart] | None = None

    async def _get_kt_chart_id(
        self, song_id: int, difficulty: Difficulty
    ) -> str | None:
        if self._kt_charts is None:
            resp = await self._client.get(
                "https://raw.githubusercontent.com/zkrising/Tachi/main/seeds/collections/charts-chunithm.json"
            )
            self._kt_charts = msgspec.json.decode(
                resp.content, type=list[KTChunithmChart]
            )

        for chart in self._kt_charts:
            if chart.data.in_game_id == song_id and chart.difficulty == str(difficulty):
                return chart.chart_id

        return None

    async def _get_kt_chart_ids(self, song_id: int) -> list[str]:
        if self._kt_charts is None:
            resp = await self._client.get(
                "https://raw.githubusercontent.com/zkrising/Tachi/main/seeds/collections/charts-chunithm.json"
            )
            self._kt_charts = msgspec.json.decode(
                resp.content, type=list[KTChunithmChart]
            )

        return [
            chart.chart_id
            for chart in self._kt_charts
            if chart.data.in_game_id == song_id
        ]

    @property
    def authentication(self) -> str:
        return self._api_key

    async def get_minimal_profile(self) -> Profile:
        resp = await self._client.get("/api/v1/users/me")
        data = msgspec.json.decode(resp.content, type=KTResponse[KTUserProfile])

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None

        user_id = data.body.id
        username = data.body.username
        custom_banner_location = data.body.custom_banner_location
        custom_pfp_location = data.body.custom_pfp_location

        if config.web.is_accessible and custom_banner_location is not None:
            request = self._client.build_request(
                "GET",
                f"https://cdn-kamai.tachi.ac/users/{user_id}/banner-{custom_banner_location}",
            )
            _ = request.headers.pop("Authorization", None)
            response = await self._client.send(request)

            try:
                mime = await guess_mime_type(response)

                if mime.startswith("image/"):
                    custom_banner_location += f".{mime[6:]}"
            finally:
                await response.aclose()

        if config.web.is_accessible and custom_pfp_location is not None:
            request = self._client.build_request(
                "GET",
                f"https://cdn-kamai.tachi.ac/users/{user_id}/pfp-{custom_pfp_location}",
            )
            _ = request.headers.pop("Authorization", None)
            response = await self._client.send(request)

            try:
                mime = await guess_mime_type(response)

                if mime.startswith("image/"):
                    custom_pfp_location += f".{mime[6:]}"
            finally:
                await response.aclose()

        return Profile(
            username=username,
            url=f"https://kamai.tachi.ac/users/{user_id}/games/chunithm/Single",
            profile_picture=(
                f"{config.web.base_url}/kamaitachi/users/{user_id}/pfp/{custom_pfp_location}"
                if config.web.is_accessible and custom_pfp_location is not None
                else None
            ),
            banner=(
                f"{config.web.base_url}/kamaitachi/users/{user_id}/banner/{custom_banner_location}"
                if config.web.is_accessible and custom_banner_location is not None
                else None
            ),
        )

    async def get_profile(self) -> Profile:
        profile = await self.get_minimal_profile()

        resp = await self._client.get("/api/v1/users/me/games/chunithm/Single")
        ugpt_data = msgspec.json.decode(
            resp.content, type=KTResponse[KTChunithmUserProfile]
        )

        if not ugpt_data.success:
            raise KamaitachiError(ugpt_data.description)

        assert ugpt_data.body is not None

        profile.rating_systems = [
            RatingSystem(
                name="NaiveRating",
                value=ugpt_data.body.game_stats.ratings.naive_rating,
            )
        ]
        profile.total_scores = ugpt_data.body.total_scores
        profile.extras = {
            "Session Playtime": f"{(ugpt_data.body.playtime) // (60 * 60 * 1000)} hours",
        }

        if (dan := ugpt_data.body.game_stats.classes.dan) is not msgspec.UNSET:
            profile.medal = getattr(SkillClass, dan.removeprefix("DAN_").lower())

        if (emblem := ugpt_data.body.game_stats.classes.emblem) is not msgspec.UNSET:
            profile.emblem = getattr(SkillClass, emblem.removeprefix("DAN_").lower())

        if (most_recent_score := ugpt_data.body.most_recent_score) is not None:
            profile.last_played = datetime.fromtimestamp(
                (most_recent_score.time_achieved or most_recent_score.time_added)
                / 1000,
                tz=UTC,
            )

        return profile

    async def get_recent_scores(self) -> list[RecentScore]:
        resp = await self._client.get(
            "/api/v1/users/me/games/chunithm/Single/scores/recent"
        )
        data = msgspec.json.decode(resp.content, type=KTChunithmScoreResponse)

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return convert_kt_scores_to_records(data.body)

    async def get_best_ratings(self) -> list[PersonalBest]:
        resp = await self._client.get(
            "/api/v1/users/me/games/chunithm/Single/pbs/best?alg=rating"
        )
        data = msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return convert_kt_pbs_to_records(data.body)

    async def get_personal_bests(self) -> list[PersonalBest]:
        resp = await self._client.get("/api/v1/users/me/games/chunithm/Single/pbs/all")
        data = msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return convert_kt_pbs_to_records(data.body)

    async def get_personal_bests_on_song(self, song_id: int) -> list[PersonalBest]:
        chart_ids = await self.get_kt_chart_ids(song_id)

        if len(chart_ids) == 0:
            msg = f"No chart exists in Kamaitachi for song ID {song_id}."
            raise SongNotFound(msg)

        fs = [
            asyncio.create_task(
                self._client.get(
                    f"/api/v1/users/me/games/chunithm/Single/pbs/{chart_id}"
                )
            )
            for chart_id in chart_ids
        ]
        tasks, _ = await asyncio.wait(fs)
        pbs: list[PersonalBest] = []

        for task in tasks:
            resp = task.result()
            data = msgspec.json.decode(
                resp.content, type=KTChunithmPersonalBestResponse
            )

            if not data.success:
                if resp.status_code == NOT_FOUND:
                    continue

                raise NetworkError(data.description)

            assert data.body is not None

            score = convert_kt_to_score(data.body.pb, "", data.body.chart)
            pbs.append(PersonalBest(**score.__dict__))

        return pbs

    async def get_chart_leaderboard(
        self, song_id: int, difficulty: Difficulty
    ) -> Leaderboard:
        chart_id = await self.get_kt_chart_id(song_id, difficulty)

        if chart_id is None:
            msg = f"No chart exists in Kamaitachi for song ID {song_id} and difficulty {difficulty}."
            raise ChartNotFound(msg)

        resp = await self._client.get(
            f"/api/v1/games/chunithm/Single/charts/{chart_id}/pbs"
        )
        data = msgspec.json.decode(resp.content, type=KTResponse[KTChunithmLeaderboard])

        if not data.success:
            raise NetworkError(data.description)

        assert data.body is not None

        users_by_id = {u.id: u for u in data.body.users}

        return Leaderboard(
            updated_at=datetime.now(UTC),
            ranking=[
                LeaderboardEntry(
                    position=i + 1,
                    player_name=users_by_id[pb.user_id].username,
                    score=pb.score_data.score,
                    judgements=(
                        Judgements(
                            justice_critical=pb.score_data.judgements.jcrit,
                            justice=pb.score_data.judgements.justice,
                            attack=pb.score_data.judgements.attack,
                            miss=pb.score_data.judgements.miss,
                        )
                        if (
                            pb.score_data.judgements.jcrit is not None
                            and pb.score_data.judgements.justice is not None
                            and pb.score_data.judgements.attack is not None
                            and pb.score_data.judgements.miss is not None
                        )
                        else None
                    ),
                    ajc_count=None,
                    achieved_at=(
                        datetime.fromtimestamp(pb.time_achieved / 1000, tz=UTC)
                        if pb.time_achieved is not None
                        else None
                    ),
                )
                for i, pb in enumerate(data.body.pbs)
            ],
        )

    async def aclose(self) -> None:
        await self._client.aclose()
