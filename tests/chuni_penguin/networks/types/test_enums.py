import pytest

from chuni_penguin.networks.types.enums import (
    ClearLamp,
    Difficulty,
    Rank,
    SkillClass,
)


def test_difficulty_from_color_is_opposite_of_difficulty_color():
    for difficulty in Difficulty:
        assert Difficulty.from_embed_color(difficulty.color()) == difficulty


def test_unknown_color_should_raise():
    with pytest.raises(ValueError):
        Difficulty.from_embed_color(0x000000)


def test_difficulty_from_short_form_is_opposite_of_difficulty_short_form():
    for difficulty in Difficulty:
        assert Difficulty(difficulty.short()) == difficulty


def test_unknown_short_form_should_raise():
    with pytest.raises(ValueError):
        Difficulty("UNK")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Difficulty.basic, "BASIC"),
        (Difficulty.advanced, "ADVANCED"),
        (Difficulty.expert, "EXPERT"),
        (Difficulty.master, "MASTER"),
        (Difficulty.ultima, "ULTIMA"),
        (Difficulty.worlds_end, "WORLD'S END"),
    ],
)
def test_difficulty_full_form(value, expected):
    assert str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (ClearLamp.failed, "FAILED"),
        (ClearLamp.clear, "CLEAR"),
        (ClearLamp.hard, "HARD"),
        (ClearLamp.brave, "BRAVE"),
        (ClearLamp.absolute, "ABSOLUTE"),
        (ClearLamp.catastrophy, "CATASTROPHY"),
    ],
)
def test_clear_type_full_form(value, expected):
    assert str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1009000, Rank.sssp),
        (1007500, Rank.sss),
        (1005000, Rank.ssp),
        (1000000, Rank.ss),
        (990000, Rank.sp),
        (975000, Rank.s),
        (950000, Rank.aaa),
        (925000, Rank.aa),
        (900000, Rank.a),
        (800000, Rank.bbb),
        (700000, Rank.bb),
        (600000, Rank.b),
        (500000, Rank.c),
        (400000, Rank.d),
        (0, Rank.d),
    ],
)
def test_rank_from_score(value, expected):
    assert Rank.from_score(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (SkillClass.i, "I"),
        (SkillClass.ii, "II"),
        (SkillClass.iii, "III"),
        (SkillClass.iv, "IV"),
        (SkillClass.v, "V"),
        (SkillClass.infinite, "∞"),
    ],
)
def test_skill_class_display_values(value, expected):
    assert str(value) == expected
