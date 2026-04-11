import asyncio
import itertools
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from http.client import NOT_FOUND
from typing import TYPE_CHECKING, ClassVar

import httpx
import httpx_aiohttp
import msgspec
from sqlalchemy import select

from chuni_penguin.adapters._hooks import raise_on_server_errors
from chuni_penguin.adapters.base import NetworkAdapter
from chuni_penguin.adapters.errors import ChartNotFound, NetworkError, SongNotFound
from chuni_penguin.adapters.utils import (
    calculate_ongeki_rating_breakdown,
    process_records,
)
from chuni_penguin.config import config
from chuni_penguin.constants import CURRENT_CHUNITHM_VERSION, ChunithmVersion
from chuni_penguin.database import Chart as DBChart
from chuni_penguin.types import (
    CourseRecord,
    Difficulty,
    Genre,
    Judgements,
    Leaderboard,
    LeaderboardEntry,
    LinkedGate,
    LinkedGateLeaderboard,
    LinkedGateStatus,
    LoginBonus,
    PersonalBest,
    Profile,
    Rank,
    RatingBreakdown,
    RatingFrame,
    RatingFrameType,
    RatingType,
    RecentScore,
)
from chuni_penguin.types.ranking import (
    CurrencyRanking,
    RankingType,
    RatingRanking,
    RatingRankingEntry,
    ScoreRanking,
    TeamRanking,
)
from chuni_penguin.utils import floor_to_ndp

from .errors import KamaitachiError
from .parser import (
    convert_kt_pbs_to_records,
    convert_kt_scores_to_records,
    convert_kt_to_score,
    guess_mime_type,
    update_profile_from_ugpt_data,
)
from .types import (
    KTChunithmChartResolveResponseBody,
    KTChunithmLeaderboard,
    KTChunithmPersonalBestResponse,
    KTChunithmPersonalBestsResponse,
    KTChunithmRanking,
    KTChunithmScoreResponse,
    KTChunithmUserProfile,
    KTResponse,
    KTUserProfile,
)

if TYPE_CHECKING:
    from chuni_penguin.cogs.database import DatabaseCog


class KamaitachiAdapter(NetworkAdapter):
    __slots__ = ("_client",)

    NAME: ClassVar[str] = "Kamaitachi"
    ACCENT_COLOR: ClassVar[int] = 0xCA1961
    DEFAULT_RATING_SYSTEM: ClassVar[RatingType] = RatingType.naive

    SUPPORTS_DETAILED_RECENT_SCORE = False

    def __init__(
        self,
        database: "DatabaseCog",
        discord_id: int,
        api_key: str,
        *args,
        base_url: str = "https://kamai.tachi.ac",
        **kwargs,
    ):
        super().__init__(database, discord_id, *args, **kwargs)

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": f"chuni-penguin (+https://github.com/beer-psi/chuni-penguin) Python/{sys.version_info[0]}.{sys.version_info[1]} httpx/{httpx.__version__}",
            },
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            event_hooks={"response": [raise_on_server_errors]},
            base_url=base_url,
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5),
        )

    async def _convert_to_minimal_profile(self, user: KTUserProfile) -> Profile:
        user_id = user.id
        username = user.username
        custom_banner_location = user.custom_banner_location
        custom_pfp_location = user.custom_pfp_location

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

    async def get_minimal_profile(self) -> Profile:
        resp = await self._client.get("/api/v1/users/me")
        data = msgspec.json.decode(resp.content, type=KTResponse[KTUserProfile])

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return await self._convert_to_minimal_profile(data.body)

    async def get_profile(self) -> Profile:
        profile = await self.get_minimal_profile()
        resp = await self._client.get(
            f"/api/v1/users/{profile.username}/games/chunithm/Single"
        )
        ugpt_data = msgspec.json.decode(
            resp.content, type=KTResponse[KTChunithmUserProfile]
        )

        if not ugpt_data.success:
            raise KamaitachiError(ugpt_data.description)

        assert ugpt_data.body is not None
        return update_profile_from_ugpt_data(profile, ugpt_data.body)

    async def get_recent_scores(self) -> list[RecentScore]:
        resp = await self._client.get(
            "/api/v1/users/me/games/chunithm/Single/scores/recent"
        )
        data = msgspec.json.decode(resp.content, type=KTChunithmScoreResponse)

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return await process_records(
            self.database,
            self.discord_id,
            self.NAME,
            convert_kt_scores_to_records(data.body),
        )

    async def get_detailed_recent_score(self, score: RecentScore) -> RecentScore:
        raise NotImplementedError

    async def get_personal_bests(
        self,
        level: str | None = None,
        difficulty: Difficulty | None = None,
        genre: Genre | None = None,
        rank: Rank | None = None,
        version: ChunithmVersion | None = None,
    ) -> list[PersonalBest]:
        pbs = await self.get_all_personal_bests()

        return [
            pb
            for pb in pbs
            if (level is None or pb.chart.level == level)
            and (difficulty is None or pb.chart.difficulty == difficulty)
            and (genre is None or pb.song.genre == genre)
            and (rank is None or pb.rank == rank)
            and (version is None or pb.song.version == version)
        ]

    async def _get_personal_bests(self, user: str | int):
        resp = await self._client.get(
            f"/api/v1/users/{user}/games/chunithm/Single/pbs/all"
        )
        data = msgspec.json.decode(resp.content, type=KTChunithmPersonalBestsResponse)

        if not data.success:
            raise KamaitachiError(data.description)

        assert data.body is not None
        return convert_kt_pbs_to_records(data.body)

    async def get_all_personal_bests(self) -> list[PersonalBest]:
        return await process_records(
            self.database,
            self.discord_id,
            self.NAME,
            await self._get_personal_bests("me"),
        )

    async def get_personal_bests_on_song(self, song_id: int) -> list[PersonalBest]:
        async with self.database.read_sessionmaker() as session:
            query = select(DBChart).where(
                (DBChart.song_id == song_id) & (DBChart.tachi_chart_id.is_not(None))
            )
            results = (await session.execute(query)).scalars()

        chart_ids = [result.tachi_chart_id for result in results]

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
            pbs.append(PersonalBest.from_score(score))

        return await process_records(self.database, self.discord_id, self.NAME, pbs)

    async def get_rating_breakdown(self, rating_type: RatingType) -> RatingBreakdown:
        if rating_type == RatingType.naive:
            resp = await self._client.get(
                "/api/v1/users/me/games/chunithm/Single/pbs/best?alg=rating"
            )
            data = msgspec.json.decode(
                resp.content, type=KTChunithmPersonalBestsResponse
            )

            if not data.success:
                raise KamaitachiError(data.description)

            assert data.body is not None

            # already sorted by rating, so no need to sort
            pbs = await process_records(
                self.database,
                self.discord_id,
                self.NAME,
                convert_kt_pbs_to_records(data.body),
            )
            pbs = pbs[:50]
            profile = await self.get_profile()
            rating = Decimal(
                next(s.value for s in profile.rating_systems if s.type == rating_type)
            )

            return RatingBreakdown(
                rating=rating,
                frames={
                    RatingFrameType.best: RatingFrame(
                        type=RatingFrameType.best,
                        num_scores=50,
                        scores=pbs,
                    )
                },
            )

        pbs = [
            pb
            for pb in await self.get_all_personal_bests()
            if pb.chart.difficulty != Difficulty.worlds_end
        ]

        if rating_type == RatingType.in_game:
            pbs.sort(
                key=lambda pb: (
                    pb.rating,
                    pb.score,
                    pb.combo_lamp,
                    pb.chart.internal_level,
                ),
                reverse=True,
            )

            best: list[PersonalBest] = []
            new: list[PersonalBest] = []

            for pb in pbs:
                if pb.song.version == CURRENT_CHUNITHM_VERSION:
                    if len(new) < 20:
                        new.append(pb)
                elif len(best) < 30:
                    best.append(pb)

                if len(best) == 30 and len(new) == 20:
                    break

            rating = floor_to_ndp(
                sum(
                    [r.rating or Decimal(0) for r in itertools.chain(best, new)],
                    start=Decimal(0),
                )
                / 50,
                2,
            )

            return RatingBreakdown(
                rating=rating,
                frames={
                    RatingFrameType.best: RatingFrame(
                        type=RatingFrameType.best, num_scores=30, scores=best
                    ),
                    RatingFrameType.new: RatingFrame(
                        type=RatingFrameType.new, num_scores=20, scores=new
                    ),
                },
            )

        if rating_type in (RatingType.ongeki, RatingType.ongeki_naive):
            return calculate_ongeki_rating_breakdown(rating_type, pbs)

        msg = f"Unknown RatingType variant {rating_type!r}"
        raise RuntimeError(msg)

    async def get_chart_leaderboard(
        self, song_id: int, difficulty: Difficulty
    ) -> Leaderboard:
        resp = await self._client.post(
            "/api/v1/games/chunithm/Single/charts/resolve",
            json={
                "matchType": "inGameID",
                "identifier": str(song_id),
                "difficulty": str(difficulty),
            },
        )
        resolve_data = msgspec.json.decode(
            resp.content, type=KTResponse[KTChunithmChartResolveResponseBody]
        )

        if not resolve_data.success or resolve_data.body is None:
            msg = f"No chart exists in Kamaitachi for song ID {song_id} and difficulty {difficulty}."
            raise ChartNotFound(msg)

        chart_id = resolve_data.body.chart.chart_id
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

    async def get_course_records(self) -> list[CourseRecord]:
        raise NotImplementedError

    async def get_login_bonus_progress(self) -> LoginBonus:
        raise NotImplementedError

    async def update_username(self, new_username: str) -> None:
        raise NotImplementedError

    async def send_friend_request(self, identifier: str) -> None:
        raise NotImplementedError

    async def get_linked_verse_progress(self) -> dict[LinkedGate, LinkedGateStatus]:
        raise NotImplementedError

    async def get_linked_gate_leaderboard(
        self, linked_gate: LinkedGate
    ) -> LinkedGateLeaderboard:
        raise NotImplementedError

    async def get_favorite_music(self) -> list[int]:
        raise NotImplementedError

    async def set_favorite_music(self, ids: Sequence[int]) -> None:
        raise NotImplementedError

    async def get_team_ranking(self, month: datetime | None = None) -> TeamRanking:
        raise NotImplementedError

    async def get_rating_ranking(
        self, type: RankingType = RankingType.global_
    ) -> RatingRanking:
        if type == RankingType.friend:
            raise NotImplementedError

        resp = await self._client.get(
            "/api/v1/games/chunithm/Single/leaderboard",
            params={"alg": "naiveRating", "limit": "500"},
        )
        data = msgspec.json.decode(resp.content, type=KTResponse[KTChunithmRanking])

        if not data.success or data.body is None:
            raise KamaitachiError(data.description)

        users_by_id = {u.id: u for u in data.body.users}
        ranking: list[RatingRankingEntry] = []
        position = 0
        num_people_same_rating = 1
        last_rating = None

        for game_stat in data.body.game_stats:
            user = users_by_id.get(game_stat.userID)

            if user is None:
                continue

            if game_stat.ratings.naive_rating == last_rating:
                num_people_same_rating += 1
            else:
                last_rating = game_stat.ratings.naive_rating
                position += num_people_same_rating
                num_people_same_rating = 1

            ranking.append(
                RatingRankingEntry(
                    position=position,
                    player_name=user.username,
                    rating=game_stat.ratings.naive_rating,
                )
            )

        return RatingRanking(updated_at=datetime.now(UTC), ranking=ranking)

    async def get_score_ranking(
        self,
        type: RankingType = RankingType.global_,
        difficulty: Difficulty | None = None,
    ) -> ScoreRanking:
        raise NotImplementedError

    async def get_currency_ranking(
        self, type: RankingType = RankingType.global_
    ) -> CurrencyRanking:
        raise NotImplementedError

    async def logout(self) -> None:
        raise NotImplementedError

    async def aclose(self) -> None:
        await self._client.aclose()
