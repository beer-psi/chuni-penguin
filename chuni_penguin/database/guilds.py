from enum import IntEnum

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UInt64Integer


class Prefix(Base):
    __tablename__ = "guild_prefix"

    guild_id: Mapped[int] = mapped_column(UInt64Integer(), primary_key=True)
    prefix: Mapped[str] = mapped_column(nullable=False)


class PrimaryPermissionTarget(IntEnum):
    guild = 0
    role = 1
    channel = 2
    user = 3


class SecondaryPermissionTarget(IntEnum):
    all = 0
    group = 1
    command = 2


class CommandPermission(Base):
    __tablename__ = "command_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(UInt64Integer())

    index: Mapped[int] = mapped_column()

    primary_target_type: Mapped[PrimaryPermissionTarget] = mapped_column()
    primary_target_id: Mapped[int] = mapped_column(UInt64Integer())

    secondary_target_type: Mapped[SecondaryPermissionTarget] = mapped_column()
    secondary_target_name: Mapped[str] = mapped_column()

    is_allowed: Mapped[bool] = mapped_column()

    __table_args__ = (
        Index(
            "ix_command_permissions_primary_target_secondary_target",
            primary_target_type,
            primary_target_id,
            secondary_target_type,
            secondary_target_name,
            unique=True,
        ),
    )
