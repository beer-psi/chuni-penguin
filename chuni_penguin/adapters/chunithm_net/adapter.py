import io
import itertools
from collections.abc import Callable, Sequence
from decimal import Decimal
from http.cookiejar import DefaultCookiePolicy, LWPCookieJar
from typing import TYPE_CHECKING, Any, override

import aiolimiter
import httpx
import httpx_aiohttp
from selectolax.lexbor import LexborHTMLParser

from chuni_penguin.adapters._hooks import raise_on_server_errors
from chuni_penguin.adapters.base import NetworkAdapter
from chuni_penguin.adapters.errors import AlreadyFriends, InvalidFriendCode
from chuni_penguin.adapters.utils import (
    calculate_ongeki_rating_breakdown,
    process_record,
    process_records,
)
from chuni_penguin.constants import CURRENT_CHUNITHM_VERSION, ChunithmVersion
from chuni_penguin.types import (
    CourseRecord,
    Difficulty,
    Friend,
    Genre,
    Leaderboard,
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
from chuni_penguin.utils import floor_to_ndp

from ._hooks import ChunithmNetAuth, acquire_ratelimit, raise_on_chunithm_net_error
from .parser import (
    parse_basic_recent_record,
    parse_collection_customize,
    parse_course_list,
    parse_detailed_recent_record,
    parse_friend_vs,
    parse_leaderboard,
    parse_linked_gate_leaderboard,
    parse_linked_verse_progress,
    parse_login_bonus,
    parse_music_for_rating,
    parse_music_record,
    parse_player_card_and_avatar,
    parse_player_data,
)

if TYPE_CHECKING:
    from chuni_penguin.cogs.database import DatabaseCog

_BASE_URL = httpx.URL("https://chunithm-net-eng.com")


class ChunithmNetAdapter(NetworkAdapter):
    __slots__ = ("_client", "_jar")

    NAME = "CHUNITHM International"
    ACCENT_COLOR = 0xFEE75C
    DEFAULT_RATING_SYSTEM = RatingType.in_game

    SUPPORTS_DETAILED_RECENT_SCORE = True

    def __init__(
        self,
        database: "DatabaseCog",
        discord_id: int,
        lwp_cookie_jar: str,
        *args,
        username: str | None = None,
        password: str | None = None,
        limiter: aiolimiter.AsyncLimiter | None = None,
        **kwargs,
    ):
        super().__init__(database, discord_id, *args, **kwargs)

        event_hooks: dict[str, list[Callable[..., Any]]] = {
            "response": [raise_on_server_errors, raise_on_chunithm_net_error],
        }

        if limiter is not None:
            event_hooks["request"] = [acquire_ratelimit(limiter)]

        self._jar = LWPCookieJar(policy=DefaultCookiePolicy(hide_cookie2=True))
        self._jar._really_load(  # type: ignore[reportAttributeAccessIssue]
            io.StringIO(lwp_cookie_jar),
            "?",
            ignore_discard=False,
            ignore_expires=False,
        )
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            cookies=self._jar,
            timeout=httpx.Timeout(timeout=60.0),
            follow_redirects=True,
            event_hooks=event_hooks,
            transport=httpx_aiohttp.AIOHTTPTransport(retries=5),
            headers={
                # clients are recommended to update this user agent
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0",
                "accept-language": "en-US,en;q=0.5",
                "upgrade-insecure-requests": "1",
                "referer": str(_BASE_URL.join("/")),
            },
        )
        self._client.auth = ChunithmNetAuth(
            self._client, username=username, password=password
        )

    async def _request_as_soup(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ):
        resp = await self._client.request(method, url, **kwargs)

        return LexborHTMLParser(resp.content, is_fragment=False)

    @property
    def _token(self):
        return self._client.cookies.get("_t", domain=_BASE_URL.host)

    @property
    def user_agent(self) -> str:
        return self._client.headers["user-agent"]

    @user_agent.setter
    def user_agent(self, value: str):
        self._client.headers["user-agent"] = value

    @property
    def lwp_cookie_jar(self) -> str:
        return "#LWP-Cookies-2.0\n" + self._jar.as_lwp_str()

    async def get_minimal_profile(self) -> Profile:
        soup = await self._request_as_soup("GET", "/mobile/home/")

        return parse_player_card_and_avatar(soup)

    async def get_profile(self) -> Profile:
        soup = await self._request_as_soup(
            "GET",
            "/mobile/home/playerData",
        )
        player_data = parse_player_data(soup)

        soup = await self._request_as_soup(
            "GET",
            "/mobile/collection/customise",
        )
        collections = parse_collection_customize(soup)
        player_data.banner = collections.nameplate

        return player_data

    async def get_recent_scores(self) -> list[RecentScore]:
        soup = await self._request_as_soup("GET", "/mobile/record/playlog")

        return await process_records(
            self.database,
            self.discord_id,
            self.NAME,
            [parse_basic_recent_record(record) for record in soup.css(".frame02.w400")],
        )

    async def get_detailed_recent_score(self, score: RecentScore) -> RecentScore:
        if (idx := score._memo) is None:
            msg = "Invalid recent score: recent score index not set"
            raise ValueError(msg) from None

        soup = await self._request_as_soup(
            "POST",
            "/mobile/record/playlog/sendPlaylogDetail/",
            data={"idx": idx, "token": self._token},
        )

        return await process_record(
            self.database,
            self.discord_id,
            self.NAME,
            parse_detailed_recent_record(soup),
        )

    async def _get_hidden_personal_bests(
        self, level: str | None = None, difficulty: Difficulty | None = None
    ):
        hidden_charts = await self.database.charts.get_hidden_on_chuninet(
            level=level, difficulty=difficulty
        )
        hidden_song_ids = {c.song_id for c in hidden_charts}
        pbs: list[PersonalBest] = []

        for song_id in hidden_song_ids:
            # get the records for the hidden chart's song id
            hidden_records = await self.get_personal_bests_on_song(song_id)

            # and insert it into our records, if a record is not already there
            pbs.extend(hidden_records)

        return pbs

    async def get_personal_bests(
        self,
        level: str | None = None,
        difficulty: Difficulty | None = None,
        genre: Genre | None = None,
        rank: Rank | None = None,
        version: ChunithmVersion | None = None,
    ) -> list[PersonalBest]:
        if level is not None:
            plus_level = level[-1] == "+"
            level_num = int(level[:-1] if plus_level else level)
            level_value = (
                level_num - 1 + max(0, level_num - 7) + (1 if plus_level else 0)
            )

            soup = await self._request_as_soup(
                "POST",
                "/mobile/record/musicLevel/sendSearch/",
                data={
                    "level": str(level_value),
                    "token": self._token,
                },
            )
            pbs = parse_music_for_rating(soup)
        elif difficulty is not None:
            if difficulty == Difficulty.worlds_end:
                soup = await self._request_as_soup(
                    "GET", "/mobile/record/worldsEndList"
                )
            else:
                soup = await self._request_as_soup(
                    "POST",
                    f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                    data={
                        "genre": "99",
                        "token": self._token,
                    },
                )

            pbs = parse_music_for_rating(soup)
        else:
            msg = "Either level or difficulty must be specified."
            raise ValueError(msg)

        hidden_pbs = await self._get_hidden_personal_bests(
            level=level, difficulty=difficulty
        )
        existing_charts = {(r.song.id, r.chart.difficulty) for r in pbs}
        pbs.extend(
            [
                pb
                for pb in hidden_pbs
                if (pb.song.id, pb.chart.difficulty) not in existing_charts
            ]
        )

        return [
            pb
            for pb in await process_records(
                self.database, self.discord_id, self.NAME, pbs
            )
            if (level is None or pb.chart.level == level)
            and (difficulty is None or pb.chart.difficulty == difficulty)
            and (genre is None or pb.song.genre == genre)
            and (rank is None or pb.rank == rank)
            and (version is None or pb.song.version == version)
        ]

    async def get_all_personal_bests(self) -> list[PersonalBest]:
        pbs: list[PersonalBest] = []

        for difficulty in Difficulty:
            if difficulty == Difficulty.worlds_end:
                soup = await self._request_as_soup(
                    "GET", "/mobile/record/worldsEndList"
                )
            else:
                soup = await self._request_as_soup(
                    "POST",
                    f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                    data={
                        "genre": "99",
                        "token": self._token,
                    },
                )

            pbs.extend(parse_music_for_rating(soup))

        hidden_pbs = await self._get_hidden_personal_bests()
        existing_charts = {(r.song.id, r.chart.difficulty) for r in pbs}
        pbs.extend(
            [
                pb
                for pb in hidden_pbs
                if (pb.song.id, pb.chart.difficulty) not in existing_charts
            ]
        )

        return await process_records(self.database, self.discord_id, self.NAME, pbs)

    async def get_personal_bests_on_song(self, song_id: int) -> list[PersonalBest]:
        if song_id >= 8000:
            soup = await self._request_as_soup(
                "POST",
                "/mobile/record/worldsEndList/sendWorldsEndDetail/",
                data={
                    "idx": song_id,
                    "token": self._token,
                },
            )
        else:
            soup = await self._request_as_soup(
                "POST",
                "/mobile/record/musicGenre/sendMusicDetail/",
                data={
                    "idx": song_id,
                    "token": self._token,
                },
            )

        return await process_records(
            self.database, self.discord_id, self.NAME, parse_music_record(soup, song_id)
        )

    async def get_best30(self) -> list[PersonalBest]:
        soup = await self._request_as_soup(
            "GET", "/mobile/home/playerData/ratingDetailBest/"
        )

        return parse_music_for_rating(soup)

    async def get_new20(self) -> list[PersonalBest]:
        soup = await self._request_as_soup(
            "GET", "/mobile/home/playerData/ratingDetailRecent/"
        )

        return parse_music_for_rating(soup)

    async def get_rating_breakdown(self, rating_type: RatingType) -> RatingBreakdown:
        if rating_type == RatingType.in_game:
            profile = await self.get_profile()
            rating = Decimal(
                next(s.value for s in profile.rating_systems if s.type == rating_type)
            )
            records: list[PersonalBest] = []
            record_slots = 30
            new_records: list[PersonalBest] = []
            new_record_slots = 20

            # in order to get extra lamp information, we get the charts that are in a player's
            # best30/new20 from the music for rating list, but we fetch the player's PBs.
            best30_charts = [
                (x.song.id, x.chart.difficulty) for x in await self.get_best30()
            ]
            new20_charts = [
                (x.song.id, x.chart.difficulty) for x in await self.get_new20()
            ]

            difficulties = sorted(
                {x[1] for x in itertools.chain(best30_charts, new20_charts)},
                key=lambda x: x.value,
            )

            for difficulty in difficulties:
                soup = await self._request_as_soup(
                    "POST",
                    f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                    data={
                        "genre": "99",
                        "token": self._token,
                    },
                )
                difficulty_records = await process_records(
                    self.database,
                    self.discord_id,
                    self.NAME,
                    parse_music_for_rating(soup),
                )

                records.extend(
                    [
                        x
                        for x in difficulty_records
                        if (x.song.id, x.chart.difficulty) in best30_charts
                    ]
                )
                new_records.extend(
                    [
                        x
                        for x in difficulty_records
                        if (x.song.id, x.chart.difficulty) in new20_charts
                    ]
                )

            # sort the fetched best30/new20 by their position in the original b30/n20 list
            records.sort(
                key=lambda x: best30_charts.index((x.song.id, x.chart.difficulty))
            )
            new_records.sort(
                key=lambda x: new20_charts.index((x.song.id, x.chart.difficulty))
            )

            hidden_songs = await self.database.songs.get_hidden_on_chuninet()

            # Sometimes, SEGA likes to hide some scores from appearing in
            # CHUNITHM-NET. This is a workaround. Basically:
            # - Fetch music records of all hidden songs
            # - For each record, check if there are already enough slots in the
            # respective new/old rating list:
            #   - If there are already enough rating slots, and if the hidden score's
            # rating is higher than the last item in the rating list, replace the last item
            # with the hidden record.
            #   - If there are not enough rating slots, just add the song as is.
            #   - Sort the list again.
            for hidden_song in hidden_songs:
                if hidden_song.version == CURRENT_CHUNITHM_VERSION:
                    chart_list = new20_charts
                    record_list = new_records
                    record_list_slots = new_record_slots
                else:
                    chart_list = best30_charts
                    record_list = records
                    record_list_slots = record_slots

                hidden_song_records = await self.get_personal_bests_on_song(
                    hidden_song.id
                )

                for hidden_song_record in hidden_song_records:
                    if (
                        hidden_song.id,
                        hidden_song_record.chart.difficulty,
                    ) in chart_list:
                        # chart is actually not hidden
                        continue

                    if len(record_list) >= record_list_slots:
                        # record list is definitely sorted by rating
                        min_rating_record = record_list[-1]

                        if hidden_song_record.rating is not None and (
                            min_rating_record.rating is None
                            or hidden_song_record.rating > min_rating_record.rating
                        ):
                            del record_list[-1]
                            chart_list.remove(
                                (
                                    min_rating_record.song.id,
                                    min_rating_record.chart.difficulty,
                                )
                            )

                            chart_list.append(
                                (hidden_song.id, hidden_song_record.chart.difficulty)
                            )
                            record_list.append(hidden_song_record)
                    else:
                        chart_list.append(
                            (hidden_song.id, hidden_song_record.chart.difficulty)
                        )
                        record_list.append(hidden_song_record)

                    record_list.sort(key=lambda r: r.rating or Decimal(0), reverse=True)

            return RatingBreakdown(
                rating=rating,
                frames={
                    RatingFrameType.best: RatingFrame(
                        type=RatingFrameType.best,
                        num_scores=record_slots,
                        scores=records,
                    ),
                    RatingFrameType.new: RatingFrame(
                        type=RatingFrameType.new,
                        num_scores=new_record_slots,
                        scores=new_records,
                    ),
                },
            )

        pbs = await self.get_all_personal_bests()

        if rating_type == RatingType.naive:
            pbs.sort(
                key=lambda pb: (
                    pb.rating,
                    pb.score,
                    pb.combo_lamp,
                    pb.chart.internal_level,
                ),
                reverse=True,
            )
            pbs = pbs[:50]
            rating = floor_to_ndp(
                sum([pb.rating or Decimal(0) for pb in pbs], start=Decimal(0)) / 50, 2
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

        if rating_type in (RatingType.ongeki, RatingType.ongeki_naive):
            return calculate_ongeki_rating_breakdown(rating_type, pbs)

        msg = f"Unknown RatingType variant {rating_type!r}"
        raise RuntimeError(msg)

    async def get_chart_leaderboard(
        self, song_id: int, difficulty: Difficulty
    ) -> Leaderboard:
        if difficulty == Difficulty.worlds_end:
            soup = await self._request_as_soup(
                "POST",
                "mobile/ranking/worldsEnd/sendWorldsEndRankingDetail/",
                data={
                    "idx": song_id,
                    "token": self._token,
                },
            )
        else:
            soup = await self._request_as_soup(
                "POST",
                "mobile/ranking/sendRankingDetail/",
                data={
                    "diff": difficulty.value,
                    "idx": song_id,
                    # "category" seems to not be required
                    "genre": "99",
                    "token": self._token,
                },
            )

        return parse_leaderboard(soup)

    async def get_course_records(self) -> list[CourseRecord]:
        soup = await self._request_as_soup("GET", "mobile/record/courseList/")

        return parse_course_list(soup)

    async def get_login_bonus_progress(self) -> LoginBonus:
        soup = await self._request_as_soup("GET", "mobile/loginBonus/")

        return parse_login_bonus(soup)

    async def update_username(self, new_username: str) -> None:
        resp = await self._client.post(
            "mobile/home/userOption/updateUserName/update/",
            data={
                "userName": new_username,
                "token": self._token,
            },
            headers={
                "Referer": str(
                    _BASE_URL.join("/mobile/home/userOption/updateUserName")
                ),
            },
        )

        if resp.url.path == "/mobile/home/userOption/":
            return

        soup = LexborHTMLParser(resp.content, is_fragment=False)

        if (error_message := soup.css_first(".text_red")) is not None:
            msg = error_message.text(strip=True)
        else:
            msg = "An unknown error happened when changing the player name."

        raise ValueError(msg)

    async def send_friend_request(self, identifier: str) -> None:
        soup = await self._request_as_soup(
            "POST",
            "mobile/friend/search/sendSearchUser/",
            data={
                "friendCode": identifier,
                "token": self._token,
            },
            headers={"Referer": str(_BASE_URL.join("/mobile/friend/search/"))},
        )

        if not soup.css_first(".btn_friend_apply"):
            if soup.css_first(".player_friend_data_left"):
                raise AlreadyFriends
            raise InvalidFriendCode

        await self._client.post(
            "mobile/friend/search/sendInvite/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("/mobile/friend/search/searchUser/"))
            },
        )

    async def get_linked_verse_progress(self) -> dict[LinkedGate, LinkedGateStatus]:
        soup = await self._request_as_soup("GET", "mobile/home/linkedVerse/")

        return parse_linked_verse_progress(soup)

    async def get_linked_gate_leaderboard(
        self, linked_gate: LinkedGate
    ) -> LinkedGateLeaderboard:
        soup = await self._request_as_soup(
            "POST",
            "mobile/home/linkedVerse/linkedVerseRanking/sendSearch/",
            data={"id": linked_gate.value, "token": self._token},
        )

        return parse_linked_gate_leaderboard(soup)

    async def get_favorite_music(self) -> list[int]:
        soup = await self._request_as_soup("GET", "mobile/home/favorite/musicList")

        return [
            int(element.attrs["value"])  # pyright: ignore[reportArgumentType]
            for element in soup.css("input[name=musicId]")
        ]

    async def set_favorite_music(self, ids: Sequence[int]) -> None:
        await self._client.post(
            "mobile/home/favorite/updateMusic/set",
            data={
                "idx": "9999",
                "music[]": [str(id) for id in ids],
                "token": self._token,
            },
            headers={
                "referer": str(_BASE_URL.join("/mobile/home/favorite/updateMusic"))
            },
        )

    async def remove_friend_request(self, identifier: str) -> None:
        await self._client.post(
            "mobile/friend/invite/cancel/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("mobile/index.php/friend/invite/")),
            },
        )

    async def get_friends(self) -> list[Friend]:
        soup = await self._request_as_soup(
            "GET",
            "mobile/friend/",
        )
        friends: list[Friend] = []

        for e in soup.css(".friend_block"):
            profile_block = e.css_first(".box_playerprofile")

            if profile_block is None:
                continue

            profile = parse_player_card_and_avatar(profile_block)
            is_favorite = e.css_first(".friend_favorite_off") is not None
            is_rival = e.css_first(".friend_score_off") is not None

            assert profile.friend_code is not None

            friends.append(
                Friend(
                    profile=profile,
                    friend_code=profile.friend_code,
                    is_favorite=is_favorite,
                    is_rival=is_rival,
                )
            )

        return friends

    async def remove_friend(self, identifier: str) -> None:
        await self._client.request(
            "POST",
            "mobile/friend/friendDetail/drop/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("mobile/friend/friendDetail/")),
            },
        )

    async def add_favorite_friend(self, identifier: str) -> None:
        await self._client.request(
            "POST",
            "mobile/friend/favoriteOn/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("mobile/friend")),
            },
        )

    async def remove_favorite_friend(self, identifier: str) -> None:
        await self._client.request(
            "POST",
            "mobile/friend/favoriteOff/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("mobile/friend")),
            },
        )

    async def get_rival_personal_bests_by_difficulty(
        self,
        identifier: str,
        difficulty: Difficulty,
        *,
        exclude_unplayed: bool = False,
        win_only: bool = False,
        lose_only: bool = False,
    ) -> list[PersonalBest]:
        data = {
            "genre": "99",
            "friend": identifier,
            "radio_diff": str(difficulty.value),
            "token": self._token,
        }

        if exclude_unplayed:
            data["playCheck"] = "on"

        if win_only:
            data["winOnly"] = "on"

        if lose_only:
            data["loseOnly"] = "on"

        soup = await self._request_as_soup(
            "POST",
            "mobile/friend/genreVs/sendBattleStart/",
            data=data,
            headers={
                "Referer": str(_BASE_URL.join("mobile/friend/genreVs")),
            },
        )

        _, pbs = parse_friend_vs(soup)

        return [pb for pb in pbs if pb.score > 0]

    @override
    async def logout(self) -> None:
        await self._client.get("mobile/home/userOption/logout/")

    @override
    async def aclose(self) -> None:
        await self._client.aclose()
