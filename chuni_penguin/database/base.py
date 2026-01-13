from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Dialect, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

INT64_MAX = 2**63 - 1
UINT64_MAX = 2**64 - 1


class DateTimeUTC(TypeDecorator[datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @property
    def python_type(self) -> type[datetime]:
        return datetime

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return value
        if not value.tzinfo:
            msg = "tzinfo is required"
            raise TypeError(msg)
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class UInt64Integer(TypeDecorator[int]):
    """
    A uint64 that's represented as an int64 with the same bit representation
    in the database.
    """

    impl = BigInteger()
    cache_ok = True

    @property
    def python_type(self) -> type[int]:
        return int

    def process_bind_param(self, value: int | None, dialect: Dialect) -> int | None:
        if value is None:
            return value

        if value < 0 or value > UINT64_MAX:
            msg = f"uint64 requires 0 <= value <= {UINT64_MAX}, got {value=}"
            raise ValueError(msg)

        if value <= INT64_MAX:
            return value

        # Reference: https://graphics.stanford.edu/~seander/bithacks.html#VariableSignExtend
        value = value & 0xFFFFFFFFFFFFFFFF
        return (value ^ 0x8000000000000000) - 0x8000000000000000

    def process_result_value(self, value: int | None, dialect: Dialect) -> int | None:
        if value is None:
            return value

        if value >= 0:
            return value

        return value & 0xFFFFFFFFFFFFFFFF


class Base(DeclarativeBase, AsyncAttrs):
    pass


Base.registry.type_annotation_map[datetime] = DateTimeUTC
