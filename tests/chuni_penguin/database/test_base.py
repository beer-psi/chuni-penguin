import struct

import pytest
from sqlalchemy import Dialect
from sqlalchemy.dialects import sqlite

from chuni_penguin.database.base import UInt64Integer


@pytest.fixture(scope="session")
def dialect() -> Dialect:
    return sqlite.dialect()


@pytest.mark.parametrize(
    "input",
    [None, 1, 2**63 - 1, 2**63, 2**64 - 1],
)
def test_uint64_decorator_bind_param(input: int | None, dialect: Dialect):
    assert UInt64Integer().process_bind_param(input, dialect) == (
        struct.unpack("<q", struct.pack("<Q", input))[0] if input is not None else None
    )


def test_uint64_decorator_bind_param_errors(dialect: Dialect):
    with pytest.raises(ValueError):
        assert UInt64Integer().process_bind_param(-1, dialect)

    with pytest.raises(ValueError):
        assert UInt64Integer().process_bind_param(2**64, dialect)


@pytest.mark.parametrize(
    "input",
    [None, 1, 2**63 - 1, -(2**63), -1],
)
def test_uint64_decorator_result_value(input: int | None, dialect: Dialect):
    assert UInt64Integer().process_result_value(input, dialect) == (
        struct.unpack("<Q", struct.pack("<q", input))[0] if input is not None else None
    )
