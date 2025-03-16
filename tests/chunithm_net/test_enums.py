import pytest

from chunithm_net.models.enums import (
    ClearType,
    Difficulty,
    Possession,
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
        assert Difficulty.from_short_form(difficulty.short_form()) == difficulty


def test_unknown_short_form_should_raise():
    with pytest.raises(ValueError):
        Difficulty.from_short_form("UNK")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Difficulty.BASIC, "BASIC"),
        (Difficulty.ADVANCED, "ADVANCED"),
        (Difficulty.EXPERT, "EXPERT"),
        (Difficulty.MASTER, "MASTER"),
        (Difficulty.ULTIMA, "ULTIMA"),
        (Difficulty.WORLDS_END, "WORLD'S END"),
    ],
)
def test_difficulty_full_form(value, expected):
    assert str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (ClearType.FAILED, "FAILED"),
        (ClearType.CLEAR, "CLEAR"),
        (ClearType.HARD, "HARD"),
        (ClearType.BRAVE, "BRAVE"),
        (ClearType.ABSOLUTE, "ABSOLUTE"),
        (ClearType.CATASTROPHY, "CATASTROPHY"),
    ],
)
def test_clear_type_full_form(value, expected):
    assert str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1009000, Rank.SSSp),
        (1007500, Rank.SSS),
        (1005000, Rank.SSp),
        (1000000, Rank.SS),
        (990000, Rank.Sp),
        (975000, Rank.S),
        (950000, Rank.AAA),
        (925000, Rank.AA),
        (900000, Rank.A),
        (800000, Rank.BBB),
        (700000, Rank.BB),
        (600000, Rank.B),
        (500000, Rank.C),
        (400000, Rank.D),
        (0, Rank.D),
    ],
)
def test_rank_from_score(value, expected):
    assert Rank.from_score(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("silver", Possession.SILVER),
        ("gold", Possession.GOLD),
        ("platinum", Possession.PLATINUM),
        ("platina", Possession.PLATINUM),
        ("rainbow", Possession.RAINBOW),
        ("", Possession.NONE),
    ],
)
def test_possession_from_str(value, expected):
    assert Possession.from_str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (SkillClass.I, "I"),
        (SkillClass.II, "II"),
        (SkillClass.III, "III"),
        (SkillClass.IV, "IV"),
        (SkillClass.V, "V"),
        (SkillClass.INFINITE, "∞"),
    ],
)
def test_skill_class_display_values(value, expected):
    assert str(value) == expected
