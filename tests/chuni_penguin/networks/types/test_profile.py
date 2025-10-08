import pytest

from chuni_penguin.networks.types.profile import Possession


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("silver", Possession.silver),
        ("gold", Possession.gold),
        ("platina", Possession.platinum),
        ("rainbow", Possession.rainbow),
        ("normal", Possession.none),
    ],
)
def test_possession_from_str(value, expected):
    assert Possession(value) == expected
