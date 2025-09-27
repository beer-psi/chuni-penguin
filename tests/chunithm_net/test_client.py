import string
from datetime import timedelta
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from random import choices

import pytest
from pytest_httpx import HTTPXMock

from chunithm_net import ChuniNet
from chunithm_net.consts import _KEY_DETAILED_PARAMS, KEY_SONG_ID
from chunithm_net.exceptions import (
    ChuniNetError,
    InvalidTokenException,
    MaintenanceException,
)
from chunithm_net.models.enums import (
    ClearType,
    ComboType,
    Difficulty,
    Possession,
    Rank,
)

BASE_DIR = Path(__file__).parent


@pytest.fixture
def clal():
    return "".join(choices(string.ascii_lowercase + string.digits, k=64))


@pytest.fixture
def jar(clal: str) -> LWPCookieJar:
    cookie = Cookie(
        version=0,
        name="clal",
        value=clal,
        port=None,
        port_specified=False,
        domain="lng-tgk-aime-gw.am-all.net",
        domain_specified=True,
        domain_initial_dot=False,
        path="/common_auth",
        path_specified=True,
        secure=False,
        expires=3856586927,  # 2092-03-17 10:08:47Z
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )
    jar = LWPCookieJar()
    jar.set_cookie(cookie)
    return jar


@pytest.fixture
def user_id():
    return "".join(choices(string.digits, k=15))


@pytest.fixture
def token():
    return "".join(choices("abcdef" + string.digits, k=32))


@pytest.mark.asyncio
async def test_client_throws_chuninet_errors(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/error/"},
    )

    with (BASE_DIR / "assets" / "100001.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/error/",
            content=f.read(),
            status_code=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    with pytest.raises(ChuniNetError, match=r"Error code 100001: An error coccured."):
        async with ChuniNet(jar) as client:
            await client.authenticate()


@pytest.mark.asyncio
async def test_client_throws_token_errors(httpx_mock: HTTPXMock, jar: LWPCookieJar):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/"},
    )

    with (BASE_DIR / "assets" / "stupid_way_to_redirect.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/",
            status_code=200,
            content=f.read(),
        )

    httpx_mock.add_response(
        method="GET",
        url="https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/",
        status_code=200,
    )

    with pytest.raises(InvalidTokenException):
        async with ChuniNet(jar) as client:
            await client.authenticate()


@pytest.mark.asyncio
async def test_client_authenticates(
    httpx_mock: HTTPXMock, jar: LWPCookieJar, clal: str
):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/"},
    )

    with (BASE_DIR / "assets" / "stupid_way_to_redirect.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/",
            status_code=200,
            content=f.read(),
        )

    httpx_mock.add_response(
        method="GET",
        url="https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/",
        status_code=302,
        headers={"Location": f"https://chunithm-net-eng.com/mobile/?ssid={clal}"},
    )
    httpx_mock.add_response(
        method="GET",
        url=f"https://chunithm-net-eng.com/mobile/?ssid={clal}",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/home/"},
    )

    with (BASE_DIR / "assets" / "logged_in_homepage.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/",
            status_code=200,
            content=f.read(),
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    async with ChuniNet(jar) as client:
        await client.authenticate()


@pytest.mark.asyncio
async def test_client_reauthenticates_on_error(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
    clal: str,
    user_id: str,
    token: str,
):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/error/"},
    )

    with (BASE_DIR / "assets" / "200004.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/error/",
            content=f.read(),
            status_code=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    httpx_mock.add_response(
        method="GET",
        url="https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/",
        status_code=302,
        headers={"Location": f"https://chunithm-net-eng.com/mobile/?ssid={clal}"},
    )

    httpx_mock.add_response(
        method="GET",
        url=f"https://chunithm-net-eng.com/mobile/?ssid={clal}",
        status_code=302,
        headers=[
            ("Location", "https://chunithm-net-eng.com/mobile/home/"),
            (
                "Set-Cookie",
                f"_t={token}; expires=Thu, 11-Aug-2033 13:09:40 GMT; Max-Age=315360000; path=/; SameSite=Strict",
            ),
            (
                "Set-Cookie",
                f"userId={user_id}; path=/; secure; HttpOnly; SameSite=Lax",
            ),
        ],
    )

    with (BASE_DIR / "assets" / "logged_in_homepage.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/",
            status_code=200,
            content=f.read(),
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    async with ChuniNet(jar) as client:
        await client.authenticate()


@pytest.mark.asyncio
async def test_client_handles_failed_reauthentication(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/"},
    )

    with (BASE_DIR / "assets" / "stupid_way_to_redirect.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/",
            status_code=200,
            content=f.read(),
        )

    httpx_mock.add_response(
        method="GET",
        url="https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/",
        status_code=200,
    )

    with pytest.raises(InvalidTokenException):
        async with ChuniNet(jar) as client:
            await client.authenticate()


@pytest.mark.asyncio
async def test_client_throws_when_on_maintenance(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/",
        status_code=503,
    )

    with pytest.raises(MaintenanceException):
        async with ChuniNet(jar) as client:
            await client.authenticate()


@pytest.mark.asyncio
async def test_client_parses_homepage(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    with (BASE_DIR / "assets" / "logged_in_homepage.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        user_data = await client.authenticate()

    assert user_data.possession == Possession.NONE

    assert (
        user_data.character
        == "https://chunithm-net-eng.com/mobile/img/2c20c7ac326c1a9d.png"
    )
    assert user_data.name == "ＢｏＡｎｈＤＬＢ"  # noqa: RUF001

    assert (
        user_data.avatar.base
        == "https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png"
    )
    assert (
        user_data.avatar.back
        == "https://chunithm-net-eng.com/mobile/img/5a278974114ddee5.png"
    )
    assert (
        user_data.avatar.skinfoot_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.skinfoot_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.skin
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.wear
        == "https://chunithm-net-eng.com/mobile/img/db379cd92224154d.png"
    )
    assert (
        user_data.avatar.face
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Face.png"
    )
    assert (
        user_data.avatar.face_cover
        == "https://chunithm-net-eng.com/mobile/img/be8557845eead739.png"
    )
    assert (
        user_data.avatar.head
        == "https://chunithm-net-eng.com/mobile/img/e037354ed1e270d5.png"
    )
    assert (
        user_data.avatar.hand_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_RightHand.png"
    )
    assert (
        user_data.avatar.hand_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_LeftHand.png"
    )
    assert (
        user_data.avatar.item_r
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )
    assert (
        user_data.avatar.item_l
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )

    assert user_data.reborn == 0
    assert user_data.lv == 11

    assert user_data.last_play_date.year == 2023
    assert user_data.last_play_date.month == 8
    assert user_data.last_play_date.day == 4
    assert user_data.last_play_date.hour == 18
    assert user_data.last_play_date.minute == 34
    assert user_data.last_play_date.tzinfo is not None
    assert user_data.last_play_date.tzinfo.utcoffset(
        user_data.last_play_date
    ) == timedelta(seconds=32400)

    assert user_data.overpower.value == pytest.approx(4878.18)
    assert user_data.overpower.progress == pytest.approx(0.0568)

    assert user_data.rating == pytest.approx(15.10)

    assert user_data.emblem is None
    assert user_data.medal is None


@pytest.mark.asyncio
async def test_client_parses_playerdata(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    with (BASE_DIR / "assets" / "player_data.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/playerData",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        user_data = await client.player_data()

    assert user_data.possession == Possession.NONE

    assert user_data.team is not None
    assert user_data.team.name == "ＣＨＵＮＩＴＨＭ　Ｆｌｅｘｉｂｌｅ"  # noqa: RUF001
    assert (
        user_data.character
        == "https://chunithm-net-eng.com/mobile/img/2c20c7ac326c1a9d.png"
    )
    assert user_data.name == "ＢｏＡｎｈＤＬＢ"  # noqa: RUF001

    assert len(user_data.titles) == 2
    assert user_data.titles[0].content == "ネコぱら"
    assert user_data.titles[0].rarity == "silver"
    assert user_data.titles[1].content == "SPIRIT of PARADISE LOST"
    assert user_data.titles[1].rarity == "version1"

    assert (
        user_data.avatar.base
        == "https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png"
    )
    assert (
        user_data.avatar.back
        == "https://chunithm-net-eng.com/mobile/img/5a278974114ddee5.png"
    )
    assert (
        user_data.avatar.skinfoot_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.skinfoot_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.skin
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.avatar.wear
        == "https://chunithm-net-eng.com/mobile/img/db379cd92224154d.png"
    )
    assert (
        user_data.avatar.face
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Face.png"
    )
    assert (
        user_data.avatar.face_cover
        == "https://chunithm-net-eng.com/mobile/img/be8557845eead739.png"
    )
    assert (
        user_data.avatar.head
        == "https://chunithm-net-eng.com/mobile/img/e037354ed1e270d5.png"
    )
    assert (
        user_data.avatar.hand_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_RightHand.png"
    )
    assert (
        user_data.avatar.hand_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_LeftHand.png"
    )
    assert (
        user_data.avatar.item_r
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )
    assert (
        user_data.avatar.item_l
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )

    assert user_data.reborn == 0
    assert user_data.lv == 11

    assert user_data.last_play_date.year == 2023
    assert user_data.last_play_date.month == 8
    assert user_data.last_play_date.day == 4
    assert user_data.last_play_date.hour == 18
    assert user_data.last_play_date.minute == 34
    assert user_data.last_play_date.tzinfo is not None
    assert user_data.last_play_date.tzinfo.utcoffset(
        user_data.last_play_date
    ) == timedelta(seconds=32400)

    assert user_data.playcount == 70

    assert user_data.overpower.value == pytest.approx(4878.18)
    assert user_data.overpower.progress == pytest.approx(0.0568)

    assert user_data.rating == pytest.approx(15.10)

    assert user_data.currency is not None
    assert user_data.currency.owned == 133500
    assert user_data.currency.total == 136000

    assert user_data.friend_code == "1234567890123"

    assert user_data.emblem is None
    assert user_data.medal is None


@pytest.mark.asyncio
async def test_client_parses_playlog(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    with (BASE_DIR / "assets" / "playlog.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/record/playlog",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        records = await client.recent_record()

    assert len(records) == 50

    record = records[0]

    assert record.extras.get(_KEY_DETAILED_PARAMS) is not None

    assert record.title == "Air"
    assert record.difficulty == Difficulty.MASTER
    assert record.score == 950592

    assert record.rank == Rank.AAA
    assert record.clear_lamp == ClearType.FAILED
    assert record.combo_lamp == ComboType.NONE

    assert (
        record.jacket == "https://chunithm-net-eng.com/mobile/img/db15d5b7aefaa672.jpg"
    )

    assert record.play_count is None

    assert record.track == 4

    assert record.date.year == 2023
    assert record.date.month == 8
    assert record.date.day == 4
    assert record.date.hour == 18
    assert record.date.minute == 33
    assert record.date.tzinfo is not None
    assert record.date.tzinfo.utcoffset(record.date) == timedelta(seconds=32400)

    assert record.new_record is True


@pytest.mark.asyncio
async def test_client_parses_detailed_playlog(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="POST",
        url="https://chunithm-net-eng.com/mobile/record/playlog/sendPlaylogDetail/",
        status_code=302,
        headers={
            "Location": "https://chunithm-net-eng.com/mobile/record/playlogDetail/"
        },
    )

    with (BASE_DIR / "assets" / "playlog_detail.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/record/playlogDetail/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        record = await client.detailed_recent_record(40)

    assert record.extras.get(KEY_SONG_ID) == 317

    assert record.title == "Air"
    assert record.difficulty == Difficulty.MASTER
    assert record.score == 950592

    assert record.rank == Rank.AAA
    assert record.clear_lamp == ClearType.FAILED
    assert record.combo_lamp == ComboType.NONE

    assert (
        record.jacket == "https://chunithm-net-eng.com/mobile/img/db15d5b7aefaa672.jpg"
    )

    assert record.play_count is None

    assert record.track == 4

    assert record.date.year == 2023
    assert record.date.month == 8
    assert record.date.day == 4
    assert record.date.hour == 18
    assert record.date.minute == 33
    assert record.date.tzinfo is not None
    assert record.date.tzinfo.utcoffset(record.date) == timedelta(seconds=32400)

    assert record.new_record is True

    assert record.character == "光"

    assert record.skill.name == "キャンペーンブースト"
    assert record.skill.grade == 1
    assert record.skill_result == 0

    assert record.max_combo == 292

    assert record.judgements.jcrit == 1430
    assert record.judgements.justice == 282
    assert record.judgements.attack == 76
    assert record.judgements.miss == 68

    assert record.note_type.tap == pytest.approx(0.9344)
    assert record.note_type.hold == pytest.approx(0.9911)
    assert record.note_type.slide == pytest.approx(0.9821)
    assert record.note_type.air == pytest.approx(0.9873)
    assert record.note_type.flick == pytest.approx(0.9957)


@pytest.mark.asyncio
async def test_client_parses_music_record(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="POST",
        url="https://chunithm-net-eng.com/mobile/record/musicGenre/sendMusicDetail/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/record/musicDetail/"},
    )

    with (BASE_DIR / "assets" / "music_record.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/record/musicDetail/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        records = await client.music_record(428)

    assert len(records) == 2

    assert (
        records[0].extras.get(KEY_SONG_ID) == records[1].extras.get(KEY_SONG_ID) == 428
    )

    assert records[0].title == records[1].title == "Aleph-0"

    assert records[0].difficulty == Difficulty.EXPERT
    assert records[1].difficulty == Difficulty.MASTER

    assert records[0].score == 1005037
    assert records[1].score == 988818

    assert records[0].rank == Rank.SSp
    assert records[1].rank == Rank.S

    assert records[0].clear_lamp == ClearType.CLEAR
    assert records[1].clear_lamp == ClearType.CLEAR
    assert records[0].combo_lamp == ComboType.NONE
    assert records[1].combo_lamp == ComboType.NONE

    assert (
        records[0].jacket
        == records[1].jacket
        == "https://chunithm-net-eng.com/mobile/img/986a1c6047f3033e.jpg"
    )

    assert records[0].play_count == records[1].play_count == 2


@pytest.mark.asyncio
async def test_clients_parses_we_music_record(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="POST",
        url="https://chunithm-net-eng.com/mobile/record/worldsEndList/sendWorldsEndDetail/",
        status_code=302,
        headers={
            "Location": "https://chunithm-net-eng.com/mobile/record/worldsEndDetail/"
        },
    )

    with (BASE_DIR / "assets" / "worlds_end_music_record.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/record/worldsEndDetail/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        records = await client.music_record(8218)

    assert len(records) == 1

    record = records[0]
    assert record.extras.get(KEY_SONG_ID) == 8218

    assert record.title == "BLUE ZONE"

    assert record.difficulty == Difficulty.WORLDS_END

    assert record.score == 953506

    assert record.rank == Rank.AAA

    assert record.clear_lamp == ClearType.CLEAR

    assert record.combo_lamp == ComboType.NONE

    assert (
        record.jacket == "https://chunithm-net-eng.com/mobile/img/2640e526c59188fc.jpg"
    )

    assert record.play_count == 1


@pytest.mark.asyncio
async def test_client_parses_music_for_rating(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    with (BASE_DIR / "assets" / "best30.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/playerData/ratingDetailBest/",
            status_code=200,
            content=f.read(),
        )

    with (BASE_DIR / "assets" / "recent10.html").open("rb") as f:
        httpx_mock.add_response(
            method="GET",
            url="https://chunithm-net-eng.com/mobile/home/playerData/ratingDetailRecent/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        best30 = await client.best30()
        new20 = await client.new20()

    assert len(best30) == 30

    assert best30[0].extras.get(KEY_SONG_ID) == 428
    assert best30[0].title == "Aleph-0"
    assert best30[0].score == 1005037
    assert best30[0].difficulty == Difficulty.EXPERT

    assert len(new20) == 10

    assert new20[0].extras.get(KEY_SONG_ID) == 2340
    assert new20[0].title == "To：Be Continued"  # noqa: RUF001
    assert new20[0].score == 1000449
    assert new20[0].difficulty == Difficulty.EXPERT


@pytest.mark.asyncio
async def test_client_parses_music_record_by_folder(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    with (BASE_DIR / "assets" / "music_record_by_level_folder.html").open("rb") as f:
        httpx_mock.add_response(
            method="POST",
            url="https://chunithm-net-eng.com/mobile/record/musicLevel/sendSearch/",
            status_code=200,
            content=f.read(),
        )

    async with ChuniNet(jar) as client:
        records = await client.music_record_by_folder(level="14")

    assert records is not None
    assert len(records) == 34

    assert records[0].extras.get(KEY_SONG_ID) == 2184
    assert records[0].title == "ENDYMION"
    assert records[0].score == 992633
    assert records[0].difficulty == Difficulty.EXPERT

    assert records[0].rank == Rank.Sp
    assert records[0].clear_lamp == ClearType.CLEAR
    assert records[0].combo_lamp == ComboType.NONE


@pytest.mark.asyncio
async def test_client_can_rename(
    httpx_mock: HTTPXMock,
    jar: LWPCookieJar,
):
    httpx_mock.add_response(
        method="POST",
        url="https://chunithm-net-eng.com/mobile/home/userOption/updateUserName/update/",
        status_code=302,
        headers={"Location": "https://chunithm-net-eng.com/mobile/home/userOption/"},
    )

    httpx_mock.add_response(
        method="GET",
        url="https://chunithm-net-eng.com/mobile/home/userOption/",
        status_code=200,
    )

    async with ChuniNet(jar) as client:
        assert await client.change_player_name("new name") is True
