import random
import string

import pytest
from chuni_penguin.networks.chunithm_net.utils import (
    difficulty_from_imgurl,
    get_rank_and_lamps,
    is_valid_clal,
)
from selectolax.lexbor import LexborHTMLParser

from chuni_penguin.types import (
    ChainLamp,
    ClearLamp,
    ComboLamp,
    Difficulty,
    Rank,
)


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_clear.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_9.png">
            </div>
            """,
            (Rank.sp, ClearLamp.clear, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_9.png">
            </div>
            """,
            (Rank.sp, ClearLamp.failed, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_clear.png">
            </div>
            """,
            (Rank.d, ClearLamp.clear, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
            </div>
            """,
            (Rank.d, ClearLamp.failed, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_clear.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_13.png">
                <img src="https://chunithm-net-eng.com/mobile/images/icon_alljustice.png">
            </div>
            """,
            (Rank.sssp, ClearLamp.clear, ComboLamp.all_justice, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_clear.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_12.png">
                <img src="https://chunithm-net-eng.com/mobile/images/icon_fullcombo.png">
            </div>
            """,
            (Rank.sss, ClearLamp.clear, ComboLamp.full_combo, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_absolute.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_13.png">
            </div>
            """,
            (Rank.sssp, ClearLamp.absolute, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_brave.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_13.png">
            </div>
            """,
            (Rank.sssp, ClearLamp.brave, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_hard.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_13.png">
            </div>
            """,
            (Rank.sssp, ClearLamp.hard, ComboLamp.none, ChainLamp.none),
        ),
        (
            """
            <div class="play_musicdata_icon clearfix">
                <!-- ◆クリア -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_catastrophy.png">
                <!-- ◆ランク -->
                <img src="https://chunithm-net-eng.com/mobile/images/icon_rank_13.png">
            </div>
            """,
            (Rank.sssp, ClearLamp.catastrophy, ComboLamp.none, ChainLamp.none),
        ),
    ],
)
def test_get_rank_and_cleartype(html, expected):
    soup = LexborHTMLParser(html, is_fragment=True)
    assert soup.root is not None
    assert get_rank_and_lamps(soup.root) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("basic", Difficulty.basic),
        ("advanced", Difficulty.advanced),
        ("expert", Difficulty.expert),
        ("master", Difficulty.master),
        ("worldsend", Difficulty.worlds_end),
        ("ultima", Difficulty.ultima),
        ("ultimate", Difficulty.ultima),
    ],
)
def test_difficulty_from_imgurl(value, expected):
    assert difficulty_from_imgurl(value) == expected


@pytest.mark.parametrize(
    ("value"),
    [
        "unknown",
        "basik",
        "advance",
        "worldend",
        "ultimat",
        "thembululwa",
    ],
)
def test_difficulty_from_imgurl_raises_on_unknown_difficulty(value):
    with pytest.raises(ValueError):
        difficulty_from_imgurl(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("".join(random.choices(string.ascii_lowercase + string.digits, k=64)), True),
        (
            "clal="
            + "".join(random.choices(string.ascii_lowercase + string.digits, k=64)),
            True,
        ),
        # AI autocomplete generated this one, but it's funny, so I'll keep it.
        (
            "thembululwa",
            False,
        ),
        ("Ｈｕｃ　Ｔｏｕｒ" * 8, False),  # noqa: RUF001
    ],
)
def test_is_valid_clal(value: str, expected: bool):  # noqa: FBT001
    assert is_valid_clal(value) is expected
