import pytest

from utils.calculation.border import calculate_border


@pytest.mark.parametrize(
    "notecount",
    [
        1223,
        4000,
        2470,
        1653,
        2171,
        1322,
        2226,
        1483,
        3000,
        1883,
        1587,
        2100,
        1106,
        1567,
        1733,
        2323,
        1213,
        2060,
        1927,
        2393,
    ],
)
def test_calculate_border(notecount: int):
    borders = calculate_border(notecount)
    score_per_justice = 1_000_000 / notecount
    score_per_jcrit = score_per_justice * 1.01
    score_per_attack = score_per_justice * 0.5

    for rank, judgements in borders.items():
        if isinstance(rank, str):
            assert rank == "99AJ"
            min_score = 1_009_900
        else:
            min_score = rank.min_score

        assert round(
            judgements.jcrit * score_per_jcrit
            + judgements.justice * score_per_justice
            + judgements.attack * score_per_attack
        ) >= min_score
