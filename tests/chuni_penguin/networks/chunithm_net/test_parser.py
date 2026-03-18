import datetime
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from pytest_benchmark.fixture import BenchmarkFixture
from selectolax.lexbor import LexborHTMLParser, LexborNode

from chuni_penguin.networks.chunithm_net.parser import (
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
from chuni_penguin.networks.consts import KEY_SONG_ID
from chuni_penguin.networks.types import (
    ClearLamp,
    ComboLamp,
    CourseClass,
    Difficulty,
    LinkedGate,
    LinkedGateStatus,
    LinkLevel,
    Possession,
    Rank,
    Rarity,
)

BASE_DIR = Path(__file__).parent


def make_lexbor_and_parse[T](
    data: bytes,
    fn: Callable[[LexborNode], T],
    *args,
    **kwargs,
) -> T:
    soup = LexborHTMLParser(data, is_fragment=False)
    assert soup.root is not None

    return fn(soup.root, *args, **kwargs)


def test_parse_player_card_and_avatar(benchmark: BenchmarkFixture):
    user_data = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "logged_in_homepage.html").read_bytes(),
        parse_player_card_and_avatar,
    )

    assert user_data.possession == Possession.none

    assert (
        user_data.profile_picture
        == "https://chunithm-net-eng.com/mobile/img/2c20c7ac326c1a9d.png"
    )
    assert user_data.username == "ＢｏＡｎｈＤＬＢ"  # noqa: RUF001

    assert user_data.user_avatar is not None
    assert (
        user_data.user_avatar.base
        == "https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png"
    )
    assert (
        user_data.user_avatar.back
        == "https://chunithm-net-eng.com/mobile/img/5a278974114ddee5.png"
    )
    assert (
        user_data.user_avatar.skinfoot_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.skinfoot_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.skin
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.wear
        == "https://chunithm-net-eng.com/mobile/img/db379cd92224154d.png"
    )
    assert (
        user_data.user_avatar.face
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Face.png"
    )
    assert (
        user_data.user_avatar.face_cover
        == "https://chunithm-net-eng.com/mobile/img/be8557845eead739.png"
    )
    assert (
        user_data.user_avatar.head
        == "https://chunithm-net-eng.com/mobile/img/e037354ed1e270d5.png"
    )
    assert (
        user_data.user_avatar.hand_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_RightHand.png"
    )
    assert (
        user_data.user_avatar.hand_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_LeftHand.png"
    )
    assert (
        user_data.user_avatar.item_r
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )
    assert (
        user_data.user_avatar.item_l
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )

    assert user_data.reincarnation_stars == 0
    assert user_data.level == 11

    assert user_data.last_played is not None
    assert user_data.last_played.year == 2023
    assert user_data.last_played.month == 8
    assert user_data.last_played.day == 4
    assert user_data.last_played.hour == 18
    assert user_data.last_played.minute == 34
    assert user_data.last_played.tzinfo is not None
    assert user_data.last_played.tzinfo.utcoffset(user_data.last_played) == timedelta(
        seconds=32400
    )

    assert user_data.over_power is not None
    assert user_data.over_power.value == pytest.approx(4878.18)
    assert user_data.over_power.percentage == pytest.approx(5.68)

    assert user_data.rating_systems[0].name == "Rating"
    assert user_data.rating_systems[0].value == pytest.approx(15.10)

    assert user_data.emblem is None
    assert user_data.medal is None


def test_parse_player_data(benchmark: BenchmarkFixture):
    user_data = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "player_data.html").read_bytes(),
        parse_player_data,
    )

    assert user_data.possession == Possession.none

    assert user_data.team is not None
    assert user_data.team.name == "ＣＨＵＮＩＴＨＭ　Ｆｌｅｘｉｂｌｅ"  # noqa: RUF001
    assert (
        user_data.profile_picture
        == "https://chunithm-net-eng.com/mobile/img/2c20c7ac326c1a9d.png"
    )
    assert user_data.username == "ＢｏＡｎｈＤＬＢ"  # noqa: RUF001

    assert len(user_data.titles) == 2
    assert user_data.titles[0].content == "ネコぱら"
    assert user_data.titles[0].rarity == Rarity.silver
    assert user_data.titles[1].content == "SPIRIT of PARADISE LOST"
    assert user_data.titles[1].rarity == Rarity.version1

    assert user_data.user_avatar is not None
    assert (
        user_data.user_avatar.base
        == "https://new.chunithm-net.com/chuni-mobile/html/mobile/images/avatar_base.png"
    )
    assert (
        user_data.user_avatar.back
        == "https://chunithm-net-eng.com/mobile/img/5a278974114ddee5.png"
    )
    assert (
        user_data.user_avatar.skinfoot_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.skinfoot_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.skin
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Skin.png"
    )
    assert (
        user_data.user_avatar.wear
        == "https://chunithm-net-eng.com/mobile/img/db379cd92224154d.png"
    )
    assert (
        user_data.user_avatar.face
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_Face.png"
    )
    assert (
        user_data.user_avatar.face_cover
        == "https://chunithm-net-eng.com/mobile/img/be8557845eead739.png"
    )
    assert (
        user_data.user_avatar.head
        == "https://chunithm-net-eng.com/mobile/img/e037354ed1e270d5.png"
    )
    assert (
        user_data.user_avatar.hand_r
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_RightHand.png"
    )
    assert (
        user_data.user_avatar.hand_l
        == "https://chunithm-net-eng.com/mobile/images/avatar/CHU_UI_Avatar_Tex_LeftHand.png"
    )
    assert (
        user_data.user_avatar.item_r
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )
    assert (
        user_data.user_avatar.item_l
        == "https://chunithm-net-eng.com/mobile/img/7beb8b81b2077bb9.png"
    )

    assert user_data.reincarnation_stars == 0
    assert user_data.level == 11

    assert user_data.last_played is not None
    assert user_data.last_played.year == 2023
    assert user_data.last_played.month == 8
    assert user_data.last_played.day == 4
    assert user_data.last_played.hour == 18
    assert user_data.last_played.minute == 34
    assert user_data.last_played.tzinfo is not None
    assert user_data.last_played.tzinfo.utcoffset(user_data.last_played) == timedelta(
        seconds=32400
    )

    assert user_data.total_credits == 70

    assert user_data.over_power is not None
    assert user_data.over_power.value == pytest.approx(4878.18)
    assert user_data.over_power.percentage == pytest.approx(5.68)

    assert user_data.rating_systems[0].name == "Rating"
    assert user_data.rating_systems[0].value == pytest.approx(15.10)

    assert user_data.currency is not None
    assert user_data.currency.owned == 133500
    assert user_data.currency.total == 136000

    assert user_data.friend_code == "1234567890123"

    assert user_data.emblem is None
    assert user_data.medal is None


def test_parse_detailed_recent_record(benchmark: BenchmarkFixture):
    record = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "playlog_detail.html").read_bytes(),
        parse_detailed_recent_record,
    )

    assert record.extras.get(KEY_SONG_ID) == 317

    assert record.title == "Air"
    assert record.difficulty == Difficulty.master
    assert record.score == 950592

    assert record.rank == Rank.aaa
    assert record.clear_lamp == ClearLamp.failed
    assert record.combo_lamp == ComboLamp.none

    assert (
        record.jacket_url
        == "https://chunithm-net-eng.com/mobile/img/db15d5b7aefaa672.jpg"
    )

    assert record.track_no == 4

    assert record.achieved_at is not None
    assert record.achieved_at.year == 2023
    assert record.achieved_at.month == 8
    assert record.achieved_at.day == 4
    assert record.achieved_at.hour == 18
    assert record.achieved_at.minute == 33
    assert record.achieved_at.tzinfo is not None
    assert record.achieved_at.tzinfo.utcoffset(record.achieved_at) == timedelta(
        seconds=32400
    )

    assert record.is_new_record is True

    assert record.character == "光"

    assert record.skill is not None
    assert record.skill.name == "キャンペーンブースト"
    assert record.skill.grade == 1
    assert record.skill_result == 0

    assert record.max_combo == 292

    assert record.judgements is not None
    assert record.judgements.justice_critical == 1430
    assert record.judgements.justice == 282
    assert record.judgements.attack == 76
    assert record.judgements.miss == 68

    assert record.note_percentage is not None
    assert record.note_percentage.tap == pytest.approx(93.44)
    assert record.note_percentage.hold == pytest.approx(99.11)
    assert record.note_percentage.slide == pytest.approx(98.21)
    assert record.note_percentage.air == pytest.approx(98.73)
    assert record.note_percentage.flick == pytest.approx(99.57)


def test_parse_music_record(benchmark: BenchmarkFixture):
    records = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "music_record.html").read_bytes(),
        parse_music_record,
        428,
    )

    assert len(records) == 2

    assert (
        records[0].extras.get(KEY_SONG_ID) == records[1].extras.get(KEY_SONG_ID) == 428
    )

    assert records[0].title == records[1].title == "Aleph-0"

    assert records[0].difficulty == Difficulty.expert
    assert records[1].difficulty == Difficulty.master

    assert records[0].score == 1005037
    assert records[1].score == 988818

    assert records[0].rank == Rank.ssp
    assert records[1].rank == Rank.s

    assert records[0].clear_lamp == ClearLamp.clear
    assert records[1].clear_lamp == ClearLamp.clear
    assert records[0].combo_lamp == ComboLamp.none
    assert records[1].combo_lamp == ComboLamp.none

    assert (
        records[0].jacket_url
        == records[1].jacket_url
        == "https://chunithm-net-eng.com/mobile/img/986a1c6047f3033e.jpg"
    )

    assert records[0].play_count == records[1].play_count == 2


def test_parse_music_for_rating(benchmark: BenchmarkFixture):
    records = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "music_record_by_level_folder.html").read_bytes(),
        parse_music_for_rating,
    )

    assert records is not None
    assert len(records) == 34

    assert records[0].extras.get(KEY_SONG_ID) == 2184
    assert records[0].title == "ENDYMION"
    assert records[0].score == 992633
    assert records[0].difficulty == Difficulty.expert

    assert records[0].rank == Rank.sp
    assert records[0].clear_lamp == ClearLamp.clear
    assert records[0].combo_lamp == ComboLamp.none


def test_parse_course_list(benchmark: BenchmarkFixture):
    courses = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "course_list.html").read_bytes(),
        parse_course_list,
    )

    assert courses[0].id == 40015
    assert courses[0].cls == CourseClass.iv
    assert courses[0].name == "TAP TAP PARADISE Set"
    assert courses[0].score == 3_015_447
    assert courses[0].rank == Rank.ssp
    assert courses[0].clear_lamp == ClearLamp.clear
    assert courses[0].combo_lamp == ComboLamp.none

    assert courses[4].id == 40021
    assert courses[4].cls == CourseClass.v
    assert courses[4].name == "CRITICAL EX CHALLENGE"
    assert courses[4].score == 3_029_908
    assert courses[4].rank == Rank.sssp
    assert courses[4].clear_lamp == ClearLamp.clear
    assert courses[4].combo_lamp == ComboLamp.all_justice

    assert courses[6].id == 40025
    assert courses[6].cls == CourseClass.infinite
    assert courses[6].name == "INNOVATION Set"
    assert courses[6].score == 0
    assert courses[6].rank == Rank.d
    assert courses[6].clear_lamp == ClearLamp.failed
    assert courses[6].combo_lamp == ComboLamp.none


def test_parse_leaderboard(benchmark: BenchmarkFixture):
    leaderboard = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "music_ranking_detail.html").read_bytes(),
        parse_leaderboard,
    )

    assert leaderboard.updated_at == datetime.datetime(
        2025, 10, 4, 6, 15, tzinfo=datetime.UTC
    )
    assert len(leaderboard.ranking) == 100
    assert leaderboard.ranking[0].position == 1
    assert leaderboard.ranking[0].score == 1_010_000
    assert leaderboard.ranking[0].player_name == "ＩＮＦД"
    assert leaderboard.ranking[0].ajc_count == 1
    assert leaderboard.ranking[0].achieved_at == datetime.datetime(
        2024, 11, 28, 11, 41, tzinfo=datetime.UTC
    )


def test_parse_collections_customise(benchmark: BenchmarkFixture):
    collections = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "collection_customise.html").read_bytes(),
        parse_collection_customize,
    )

    assert len(collections.titles) == 2

    assert (
        collections.titles[0].content
        == "Phosphoribosylaminoimidazolesuccinocarboxamide"
    )
    assert collections.titles[0].rarity == Rarity.platinum

    assert collections.titles[1].content == "Should be burning in hell."
    assert collections.titles[1].rarity == Rarity.silver

    assert (
        collections.nameplate
        == "https://chunithm-net-eng.com/mobile/img/14c0bda1b8026041.png"
    )

    assert (
        collections.map_icon
        == "https://chunithm-net-eng.com/mobile/img/60df318292eae46b.png"
    )

    assert (
        collections.system_voice
        == "https://chunithm-net-eng.com/mobile/img/b54ab119af308f73.png"
    )


def test_parse_login_bonus(benchmark: BenchmarkFixture):
    login_bonus = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "login_bonus.html").read_bytes(),
        parse_login_bonus,
    )

    assert len(login_bonus.monthly_login_bonus) == 1

    monthly_bonus = login_bonus.monthly_login_bonus[0]

    assert monthly_bonus.name == "Oct 2025 Login Bonus"
    assert monthly_bonus.days_logged_in == 5
    assert len(monthly_bonus.rewards) == 10

    assert (
        monthly_bonus.rewards[0].name == "CHARACTER EXP BOOST ×6.0"  # noqa: RUF001
    )
    assert (
        monthly_bonus.rewards[0].icon_url
        == "https://chunithm-net-eng.com/mobile//img/58920c78d8363d42.png"
    )
    assert monthly_bonus.rewards[0].day == 3
    assert monthly_bonus.rewards[0].obtained

    assert (
        monthly_bonus.rewards[1].name == "CHARACTER EXP BOOST ×6.0"  # noqa: RUF001
    )
    assert (
        monthly_bonus.rewards[1].icon_url
        == "https://chunithm-net-eng.com/mobile//img/58920c78d8363d42.png"
    )
    assert monthly_bonus.rewards[1].day == 6
    assert not monthly_bonus.rewards[1].obtained

    assert len(login_bonus.login_bonus) == 14
    assert login_bonus.login_bonus[0].name == "5000メモリー"
    assert (
        login_bonus.login_bonus[0].icon_url
        == "https://chunithm-net-eng.com/mobile/images/GameCurrency_v230.png"
    )
    assert login_bonus.login_bonus[0].day == 15
    assert login_bonus.login_bonus[0].obtained

    assert not login_bonus.login_bonus[11].obtained

    assert login_bonus.daily_bonus[0].weekday_name == "Monday"
    assert (
        login_bonus.daily_bonus[0].icon_url
        == "https://chunithm-net-eng.com/mobile//images/bonus_icon_exp.png"
    )
    assert login_bonus.daily_bonus[0].bonus == "キャラクターEXP×1.5"  # noqa: RUF001
    assert not login_bonus.daily_bonus[0].is_today

    assert login_bonus.daily_bonus[2].is_today


def test_parse_linked_verse_progress(benchmark: BenchmarkFixture):
    progress = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "linked_verse.html").read_bytes(),
        parse_linked_verse_progress,
    )

    assert progress[LinkedGate.origin] == LinkedGateStatus.not_found
    assert progress[LinkedGate.air] == LinkedGateStatus.under_analysis
    assert progress[LinkedGate.star] == LinkedGateStatus.linkable
    assert progress[LinkedGate.amazon] == LinkedGateStatus.clear


def test_parse_linked_gate_leaderboard(benchmark: BenchmarkFixture):
    leaderboard = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "linked_verse_ranking.html").read_bytes(),
        parse_linked_gate_leaderboard,
    )

    assert leaderboard.title == "OUTRAGE"
    assert leaderboard.artist == "USAO vs DJ Myosuke"
    assert (
        leaderboard.jacket_url
        == "https://chunithm-net-eng.com/mobile/img/f4150a747aa00ceb.jpg"
    )
    assert leaderboard.cleared_at is None
    assert leaderboard.updated_at == datetime.datetime(
        2026, 2, 4, 6, 18, tzinfo=datetime.UTC
    )

    assert leaderboard.ranking[0].position == 1
    assert leaderboard.ranking[0].player_name == "ＭＡＤＨＯＬＩＣ"  # noqa: RUF001
    assert leaderboard.ranking[0].achieved_at == datetime.datetime(
        2026, 1, 21, 23, 35, tzinfo=datetime.UTC
    )
    assert leaderboard.ranking[0].link_level == LinkLevel.v

    assert leaderboard.ranking[41].position == 42
    assert leaderboard.ranking[41].link_level == LinkLevel.iv


def test_parse_friend_vs(benchmark: BenchmarkFixture):
    _, pbs = benchmark(
        make_lexbor_and_parse,
        (BASE_DIR / "assets" / "friend_vs.html").read_bytes(),
        parse_friend_vs,
    )

    assert pbs[0].title == "きゅびずむ"
    assert pbs[0].score == 1_009_943
    assert pbs[0].combo_lamp == ComboLamp.all_justice
