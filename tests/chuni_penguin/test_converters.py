import pytest
from discord.ext import commands

from chuni_penguin.converters import (
    DifficultyConverter,
    GenreConverter,
    Level,
    LevelConverter,
    LevelRange,
    LevelRangeConverter,
    RankConverter,
)
from chuni_penguin.networks.types import Difficulty, Genre, Rank


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ["input", "output"],
    [
        ("bas", Difficulty.basic),
        ("bsc", Difficulty.basic),
        ("basic", Difficulty.basic),
        ("adv", Difficulty.advanced),
        ("advanced", Difficulty.advanced),
        ("exp", Difficulty.expert),
        ("expert", Difficulty.expert),
        ("mas", Difficulty.master),
        ("mst", Difficulty.master),
        ("master", Difficulty.master),
        ("we", Difficulty.worlds_end),
        ("wed", Difficulty.worlds_end),
        ("world's end", Difficulty.worlds_end),
        ("worldsend", Difficulty.worlds_end),
        ("worlds end", Difficulty.worlds_end),
    ],
)
async def test_difficulty_converter(input: str, output: Difficulty):
    # Context object is not actually required for conversion
    assert await DifficultyConverter().convert(None, input) == output  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ["input", "output"],
    [
        ("pops", Genre.pops_and_anime),
        ("anime", Genre.pops_and_anime),
        ("pna", Genre.pops_and_anime),
        ("p&a", Genre.pops_and_anime),
        ("pops & anime", Genre.pops_and_anime),
        ("pops&anime", Genre.pops_and_anime),
        ("niconico", Genre.niconico),
        ("vocaloid", Genre.niconico),
        ("nicovoca", Genre.niconico),
        ("niconico & vocaloid", Genre.niconico),
        ("touhou", Genre.touhou_project),
        ("toho", Genre.touhou_project),
        ("東方", Genre.touhou_project),
        ("東方Project", Genre.touhou_project),
        ("东方", Genre.touhou_project),
        ("东方Project", Genre.touhou_project),
        ("touhou project", Genre.touhou_project),
        ("original", Genre.original),
        ("chunithm", Genre.original),
        ("orig", Genre.original),
        ("chuni", Genre.original),
        ("ori", Genre.original),
        ("chu", Genre.original),
        ("variety", Genre.variety),
        ("var", Genre.variety),
        ("irodori", Genre.irodorimidori),
        ("irodorimidori", Genre.irodorimidori),
        ("iro", Genre.irodorimidori),
        ("イロドリ", Genre.irodorimidori),
        ("irdr", Genre.irodorimidori),
        ("ongeki", Genre.gekimai),
        ("maimai", Genre.gekimai),
        ("gekimai", Genre.gekimai),
        ("maigeki", Genre.gekimai),
        ("ゲキ", Genre.gekimai),
        ("マイ", Genre.gekimai),
        ("ゲキマイ", Genre.gekimai),
    ],
)
async def test_genre_converter(input: str, output: Genre):
    # Context object is not actually required for conversion
    assert await GenreConverter().convert(None, input) == output  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ["input", "output"],
    [(rank.name, rank) for rank in Rank]
    + [(rank.name.replace("p", "+"), rank) for rank in Rank if rank.name.endswith("+")],
)
async def test_rank_converter(input: str, output: Rank):
    # Context object is not actually required for conversion
    assert await RankConverter().convert(None, input) == output  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_level_converter():
    converter = LevelConverter()

    level = await converter.convert(None, "14")  # pyright: ignore[reportArgumentType]
    assert level.level == "14"
    assert level.const is None
    assert level.inferred_const == pytest.approx(14.0)
    assert level.inferred_max_const == pytest.approx(14.4)

    level = await converter.convert(None, "14+")  # pyright: ignore[reportArgumentType]
    assert level.level == "14+"
    assert level.const is None
    assert level.inferred_const == pytest.approx(14.5)
    assert level.inferred_max_const == pytest.approx(14.9)

    level = await converter.convert(None, "14.3")  # pyright: ignore[reportArgumentType]
    assert level.level == "14"
    assert level.const == pytest.approx(14.3)
    assert level.inferred_const == pytest.approx(14.3)
    assert level.inferred_max_const == pytest.approx(14.3)


@pytest.mark.asyncio
async def test_level_range_converter():
    converter = LevelRangeConverter()

    level_range = await converter.convert(None, "14")  # pyright: ignore[reportArgumentType]
    assert isinstance(level_range, Level)

    level_range = await converter.convert(None, "14-14+")  # pyright: ignore[reportArgumentType]
    assert isinstance(level_range, LevelRange)
    assert level_range.min_level is not None
    assert level_range.min_level.level == "14"
    assert level_range.max_level is not None
    assert level_range.max_level.level == "14+"

    level_range = await converter.convert(None, "14-")  # pyright: ignore[reportArgumentType]
    assert isinstance(level_range, LevelRange)
    assert level_range.min_level is not None
    assert level_range.min_level.level == "14"
    assert level_range.max_level is None

    level_range = await converter.convert(None, "-14")  # pyright: ignore[reportArgumentType]
    assert isinstance(level_range, LevelRange)
    assert level_range.min_level is None
    assert level_range.max_level is not None
    assert level_range.max_level.level == "14"

    level_range = await converter.convert(None, "14.3-14+")  # pyright: ignore[reportArgumentType]
    assert isinstance(level_range, LevelRange)
    assert level_range.min_level is not None
    assert level_range.min_level.const == pytest.approx(14.3)
    assert level_range.max_level is not None
    assert level_range.max_level.level == "14+"

    with pytest.raises(commands.BadArgument):
        await converter.convert(None, "14+-14.3")  # pyright: ignore[reportArgumentType]
