import io
from collections.abc import Sequence
from http.cookiejar import DefaultCookiePolicy, LWPCookieJar
from typing import Any, override

import httpx
import httpx_aiohttp
from bs4 import BeautifulSoup

from chuni_penguin.networks._hooks import raise_on_server_errors
from chuni_penguin.networks.base import Network
from chuni_penguin.networks.errors import AlreadyFriends, InvalidFriendCode
from chuni_penguin.networks.types import (
    CourseRecord,
    Difficulty,
    Friend,
    Leaderboard,
    LinkedGate,
    LinkedGateLeaderboard,
    LinkedGateStatus,
    LoginBonus,
    PersonalBest,
    Profile,
    RecentScore,
)

from ._bs4 import BS4_FEATURE
from ._hooks import ChunithmNetAuth, raise_on_chunithm_net_error
from .consts import _KEY_DETAILED_PARAMS_IDX
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

_BASE_URL = httpx.URL("https://chunithm-net-eng.com")


class ChunithmNet(Network):
    NAME = "CHUNITHM International"
    ACCENT_COLOR = 0xFEE75C

    RANDOMIZE_USER_AGENT = True
    DEFAULT_RATING_SYSTEM = "Rating"

    SUPPORTS_LOGOUT = True
    SUPPORTS_PROFILE = True
    SUPPORTS_USER_AVATAR_IN_PROFILE = True
    SUPPORTS_RECENT_SCORES = True
    SUPPORTS_DETAILED_RECENT_SCORE = True
    SUPPORTS_PERSONAL_BESTS_BY_LEVEL = True
    SUPPORTS_PERSONAL_BESTS_BY_DIFFICULTY = True
    SUPPORTS_PERSONAL_BESTS_ON_SONG = True
    SUPPORTS_BEST30 = True
    SUPPORTS_NEW20 = True
    SUPPORTS_CHART_LEADERBOARD = True
    SUPPORTS_COURSE_RECORDS = True
    SUPPORTS_LOGIN_BONUS_PROGRESS = True
    SUPPORTS_UPDATE_USERNAME = True
    SUPPORTS_FRIEND_REQUEST = True
    SUPPORTS_FRIENDS = True
    SUPPORTS_FAVORITE_FRIENDS = True
    SUPPORTS_RIVALS = True
    SUPPORTS_LINKED_VERSE_PROGRESS = True
    SUPPORTS_LINKED_GATE_LEADERBOARD = True
    SUPPORTS_FAVORITE_MUSIC = True
    SUPPORTS_SET_FAVORITE_MUSIC = True

    __slots__ = ("_client", "_jar")

    def __init__(
        self,
        authentication: str,
        *,
        username: str | None = None,
        password: str | None = None,
    ):
        self._jar = LWPCookieJar(policy=DefaultCookiePolicy(hide_cookie2=True))
        self._jar._really_load(  # type: ignore[reportAttributeAccessIssue]
            io.StringIO(authentication),
            "?",
            ignore_discard=False,
            ignore_expires=False,
        )
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            cookies=self._jar,
            timeout=httpx.Timeout(timeout=60.0),
            follow_redirects=True,
            event_hooks={
                "response": [raise_on_server_errors, raise_on_chunithm_net_error]
            },
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

    async def _request_as_soup(self, method: str, url: str, **kwargs: Any):
        resp = await self._client.request(method, url, **kwargs)

        return BeautifulSoup(resp.content, BS4_FEATURE)

    @property
    def _token(self):
        return self._client.cookies.get("_t", domain=_BASE_URL.host)

    @property
    def authentication(self) -> str:
        return "#LWP-Cookies-2.0\n" + self._jar.as_lwp_str()

    @property
    @override
    def user_agent(self) -> str:
        return self._client.headers["user-agent"]

    @user_agent.setter
    @override
    def user_agent(self, value: str):
        self._client.headers["user-agent"] = value

    @override
    async def logout(self) -> None:
        await self._client.get("mobile/home/userOption/logout/")

    async def get_minimal_profile(self) -> Profile:
        soup = await self._request_as_soup("GET", "/mobile/home/")

        return parse_player_card_and_avatar(soup)

    async def get_profile(self) -> Profile:
        soup = await self._request_as_soup("GET", "/mobile/home/playerData")
        player_data = parse_player_data(soup)

        soup = await self._request_as_soup("GET", "/mobile/collection/customise")
        collections = parse_collection_customize(soup)
        player_data.banner = collections.nameplate

        return player_data

    async def get_recent_scores(self) -> list[RecentScore]:
        soup = await self._request_as_soup("GET", "/mobile/record/playlog")
        web_records = soup.select(".frame02.w400")

        return [parse_basic_recent_record(record) for record in web_records]

    async def get_detailed_recent_score(self, score: RecentScore) -> RecentScore:
        try:
            idx = score.extras[_KEY_DETAILED_PARAMS_IDX]
        except KeyError:
            msg = "Invalid recent score: recent score index not set"
            raise ValueError(msg) from None

        soup = await self._request_as_soup(
            "POST",
            "/mobile/record/playlog/sendPlaylogDetail/",
            data={"idx": idx, "token": self._token},
        )

        return parse_detailed_recent_record(soup)

    async def get_personal_bests_by_level(self, level: str) -> list[PersonalBest]:
        plus_level = level[-1] == "+"
        level_num = int(level[:-1] if plus_level else level)
        level_value = level_num - 1 + max(0, level_num - 7) + (1 if plus_level else 0)

        soup = await self._request_as_soup(
            "POST",
            "/mobile/record/musicLevel/sendSearch/",
            data={
                "level": str(level_value),
                "token": self._token,
            },
        )

        return parse_music_for_rating(soup)

    async def get_personal_bests_by_difficulty(
        self, difficulty: Difficulty
    ) -> list[PersonalBest]:
        if difficulty == Difficulty.worlds_end:
            soup = await self._request_as_soup("GET", "/mobile/record/worldsEndList")
        else:
            soup = await self._request_as_soup(
                "POST",
                f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                data={
                    "genre": "99",
                    "token": self._token,
                },
            )

        return parse_music_for_rating(soup)

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

        return parse_music_record(soup, song_id)

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

        text = "".join([part async for part in resp.aiter_text()])
        soup = BeautifulSoup(text, BS4_FEATURE)

        if (error_message := soup.select_one(".text_red")) is not None:
            msg = error_message.get_text(strip=True)
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

        if not soup.select_one(".btn_friend_apply"):
            if soup.select_one(".player_friend_data_left"):
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
        soup = await self._request_as_soup("GET", "mobile/friend/")
        friends: list[Friend] = []

        for e in soup.select(".friend_block"):
            profile_block = e.select_one(".box_playerprofile")

            if profile_block is None:
                continue

            profile = parse_player_card_and_avatar(profile_block)
            is_favorite = e.select_one(".friend_favorite_off") is not None
            is_rival = e.select_one(".friend_score_off") is not None

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

    async def add_rival(self, identifier: str) -> None:
        await self._client.request(
            "POST",
            "mobile/friend/friendscoreOn/",
            data={
                "idx": identifier,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("mobile/friend")),
            },
        )

    async def remove_rival(self, identifier: str) -> None:
        await self._client.request(
            "POST",
            "mobile/friend/friendscoreOff/",
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

        return [int(element["value"]) for element in soup.select("input[name=musicId]")]  # pyright: ignore[reportArgumentType]

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

    async def aclose(self) -> None:
        await self._client.aclose()
