import dataclasses
from http.cookiejar import CookieJar
from typing import TYPE_CHECKING, Optional

import httpx
from bs4 import BeautifulSoup

from chunithm_net.models.leaderboard import Leaderboard, LeaderboardEntry

from ._bs4 import BS4_FEATURE
from ._httpx_hooks import raise_on_chunithm_net_error, raise_on_scheduled_maintenance
from .consts import _KEY_DETAILED_PARAMS
from .exceptions import (
    AlreadyAddedAsFriend,
    ChuniNetError,
    InvalidFriendCode,
    InvalidTokenException,
)
from .models.enums import Difficulty, Genres, Rank
from .models.record import MusicRecord, RecentRecord, Record
from .parser import (
    parse_basic_recent_record,
    parse_course_list,
    parse_detailed_recent_record,
    parse_music_for_rating,
    parse_music_record,
    parse_player_card_and_avatar,
    parse_player_data,
)
from .utils import chuni_int, parse_time

if TYPE_CHECKING:
    from chunithm_net.models.player_data import PlayerData

__all__ = ["ChuniNet"]

_AUTHENTICATION_URL = httpx.URL(
    "https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/"
)
_BASE_URL = httpx.URL("https://chunithm-net-eng.com")


class ChuniNet:
    def __init__(self, cookies: CookieJar) -> None:
        self.session = httpx.AsyncClient(
            cookies=cookies,
            event_hooks={
                "response": [
                    raise_on_scheduled_maintenance,
                    raise_on_chunithm_net_error,
                ],
            },
            timeout=httpx.Timeout(timeout=60.0),
            follow_redirects=True,
            transport=httpx.AsyncHTTPTransport(retries=5),
            headers={
                # clients are recommended to update this user agent
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0",
                "accept-language": "en-US,en;q=0.5",
                "upgrade-insecure-requests": "1",
                "referer": "https://chunithm-net-eng.com/",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, type, value, traceback):
        await self.session.aclose()

    async def close(self):
        await self.session.aclose()

    async def authenticate(self) -> "PlayerData":
        soup = await self._request_soup("GET", "/mobile/home/")

        return parse_player_card_and_avatar(soup)

    async def player_data(self):
        soup = await self._request_soup("GET", "/mobile/home/playerData")

        return parse_player_data(soup)

    async def recent_record(self) -> list[RecentRecord]:
        soup = await self._request_soup("GET", "/mobile/record/playlog")
        web_records = soup.select(".frame02.w400")

        return [parse_basic_recent_record(record) for record in web_records]

    async def detailed_recent_record(self, recent_record: RecentRecord | int):
        if isinstance(recent_record, int):
            params = {
                "idx": recent_record,
                "token": self._token,
            }
        else:
            params = dataclasses.asdict(recent_record.extras[_KEY_DETAILED_PARAMS])

        soup = await self._request_soup(
            "POST",
            "/mobile/record/playlog/sendPlaylogDetail/",
            data=params,
        )

        return parse_detailed_recent_record(soup)

    async def music_record(self, idx: int) -> list[MusicRecord]:
        if idx >= 8000:
            return await self._worlds_end_music_record(idx)

        soup = await self._request_soup(
            "POST",
            "/mobile/record/musicGenre/sendMusicDetail/",
            data={
                "idx": idx,
                "token": self._token,
            },
        )

        return parse_music_record(soup, idx)

    async def _worlds_end_music_record(self, idx: int) -> list[MusicRecord]:
        soup = await self._request_soup(
            "POST",
            "/mobile/record/worldsEndList/sendWorldsEndDetail/",
            data={
                "idx": idx,
                "token": self._token,
            },
        )

        return parse_music_record(soup, idx)

    async def best30(self) -> list[Record]:
        soup = await self._request_soup(
            "GET", "/mobile/home/playerData/ratingDetailBest/"
        )

        return parse_music_for_rating(soup)

    async def recent10(self) -> list[Record]:
        soup = await self._request_soup(
            "GET", "/mobile/home/playerData/ratingDetailRecent/"
        )

        return parse_music_for_rating(soup)

    async def music_record_by_folder(
        self,
        *,
        level: Optional[str] = None,
        genre: Optional[Genres] = None,
        rank: Optional[Rank] = None,
        difficulty: Optional[Difficulty] = None,
    ) -> list[Record]:
        """Get records for all songs matching specific criteria.

        CHUNITHM-NET only supports level, genre and rank search, so if multiple
        criteria are specified, they are applied in order of:
        - difficulty if difficulty is `Difficulty.WORLDS_END`
        - level
        - genre + difficulty
        - rank + difficulty
        - difficulty

        Parameters
        ----------
        level: Optional[str]
            Song level to filter by. Between 1 and 15. From level 7 to 14, can be
            suffixed with "+".
        genre: Optional[Genres]
            Genre to filter by. If this is set, `difficulty` must also be set.
        rank: Optional[Rank]
            Rank to filter by. If this is set, `difficulty` must also be set.
        difficulty: Optional[Difficulty]
            Difficulty to filter by.

        Returns
        -------
        list[Record]: List of records matching the criteria.

        Exceptions
        ----------
        ValueError:
            When genre/rank is specified but difficulty is not set, or when no
            criteria is provided.
        """
        if difficulty == Difficulty.WORLDS_END:
            soup = await self._request_soup("GET", "/mobile/record/worldsEndList")
        elif level is not None:
            plus_level = level[-1] == "+"
            level_num = int(level[:-1] if plus_level else level)
            level_value = (
                level_num - 1 + max(0, level_num - 7) + (1 if plus_level else 0)
            )

            soup = await self._request_soup(
                "POST",
                "/mobile/record/musicLevel/sendSearch/",
                data={
                    "level": str(level_value),
                    "token": self._token,
                },
            )
        elif genre is not None:
            if difficulty is None:
                msg = "Difficulty cannot be None when genre is specified"
                raise ValueError(msg)

            soup = await self._request_soup(
                "POST",
                f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                data={
                    "genre": genre.value,
                    "token": self._token,
                },
            )
        elif rank is not None:
            if difficulty is None:
                msg = "Difficulty cannot be None when genre is specified"
                raise ValueError(msg)

            value = rank.value
            if value < Rank.S.value:
                value = 7

            soup = await self._request_soup(
                "POST",
                f"/mobile/record/musicRank/send{str(difficulty).capitalize()}",
                data={
                    "rank": str(rank.value),
                    "token": self._token,
                },
            )
        elif difficulty is not None:
            soup = await self._request_soup(
                "POST",
                f"/mobile/record/musicGenre/send{str(difficulty).capitalize()}",
                data={
                    "genre": "99",
                    "token": self._token,
                },
            )
        else:
            msg = "No search criteria specified"
            raise ValueError(msg)

        return parse_music_for_rating(soup)

    async def course_record(self):
        soup = await self._request_soup("GET", "mobile/record/courseList/")

        return parse_course_list(soup)

    async def change_player_name(self, new_name: str) -> bool:
        resp = await self._request(
            "POST",
            "mobile/home/userOption/updateUserName/update/",
            data={
                "userName": new_name,
                "token": self._token,
            },
            headers={
                "Referer": str(
                    _BASE_URL.join("/mobile/home/userOption/updateUserName")
                ),
            },
        )

        if resp.url.path == "/mobile/home/userOption/":
            return True

        text = "".join([part async for part in resp.aiter_text()])
        soup = BeautifulSoup(text, BS4_FEATURE)

        if (error_message := soup.select_one(".text_red")) is not None:
            msg = error_message.get_text(strip=True)
        else:
            msg = "An unknown error happened when changing the player name."

        raise ValueError(msg)

    async def logout(self) -> bool:
        resp = await self._request("GET", "mobile/home/userOption/logout/")
        return resp.url.host == _AUTHENTICATION_URL.host

    async def send_friend_request(self, friend_code: str):
        soup = await self._request_soup(
            "POST",
            "mobile/friend/search/sendSearchUser/",
            data={
                "friendCode": friend_code,
                "token": self._token,
            },
            headers={"Referer": str(_BASE_URL.join("/mobile/friend/search/"))},
        )

        if not soup.select_one(".btn_friend_apply"):
            if soup.select_one(".player_friend_data_left"):
                raise AlreadyAddedAsFriend
            raise InvalidFriendCode

        await self._request(
            "POST",
            "mobile/friend/search/sendInvite/",
            data={
                "idx": friend_code,
                "token": self._token,
            },
            headers={
                "Referer": str(_BASE_URL.join("/mobile/friend/search/searchUser/"))
            },
        )

    async def music_leaderboard(self, idx: int, difficulty: Difficulty):
        soup = await self._request_soup(
            "POST",
            "mobile/ranking/sendRankingDetail/",
            data={
                "diff": difficulty.value,
                "idx": idx,
                # "category" seems to not be required
                "genre": "99",
                "token": self._token,
            },
        )

        updated_at_elem = soup.select_one(".ranking_update")

        if updated_at_elem is None:
            msg = "Could not find leaderboard update date."
            raise ValueError(msg)

        lb = Leaderboard(
            updated_at=parse_time(updated_at_elem.text.removeprefix("Update on：")),  # noqa: RUF001
            ranking=[],
        )

        for entry in soup.select(".rank_block"):
            position_elem = entry.select_one(".rank_block_rank")
            player_name_elem = entry.select_one(".rank_block_name")
            score_elem = entry.select_one(".rank_score_block .rank_block_num")
            ajc_count_elem = entry.select_one(
                ".rank_score_block .rank_block_theory_text"
            )
            last_raised_elem = entry.select_one(
                ".rank_block_date, .rank_block_date_new"
            )

            if (
                position_elem is None
                or player_name_elem is None
                or score_elem is None
                or last_raised_elem is None
            ):
                continue

            lb_entry = LeaderboardEntry(
                position=chuni_int(position_elem.text),
                player_name=player_name_elem.text,
                score=chuni_int(score_elem.text),
                ajc_count=chuni_int(ajc_count_elem.text)
                if ajc_count_elem is not None
                else None,
                last_raised=parse_time(last_raised_elem.text),
            )
            lb.ranking.append(lb_entry)

        return lb

    @property
    def _token(self):
        return self.session.cookies.get("_t", domain=_BASE_URL.host)

    async def _request_soup(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> BeautifulSoup:
        resp = await self._request(method, path, **kwargs)
        text = "".join([part async for part in resp.aiter_text()])

        return BeautifulSoup(text, BS4_FEATURE)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = _BASE_URL.join(path)

        try:
            response = await self.session.request(method, url, **kwargs)

            if response.url.path == "/mobile/":
                await response.aclose()

                raise ChuniNetError(200004, "")  # noqa: TRY301
        except ChuniNetError as e:
            if e.code not in {
                200004,  # invalid session
                200002,  # connection time expired
            }:
                raise
        else:
            return response

        auth_response = await self.session.get(_AUTHENTICATION_URL)

        if auth_response.url.host == _AUTHENTICATION_URL.host:
            await auth_response.aclose()
            raise InvalidTokenException

        if str(url) == str(auth_response.url):
            return auth_response

        await auth_response.aclose()
        return await self.session.request(method, url, **kwargs)
