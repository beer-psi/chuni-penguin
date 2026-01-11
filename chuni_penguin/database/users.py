from sqlalchemy import BigInteger, Boolean, Index, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Cookie(Base):
    __tablename__ = "cookies"

    discord_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    cookie: Mapped[str] = mapped_column(String(64), nullable=False)
    kamaitachi_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_contributor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    is_supporter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )


class UserConfig(Base):
    __tablename__ = "user_configs"
    __table_args__ = (Index("ix_user_configs_discord_id", "discord_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger(), unique=True)
    synthesis_alt_jacket: Mapped[str] = mapped_column()
    privacy_mode: Mapped[bool] = mapped_column(
        default=False, server_default=text("FALSE")
    )


class EasterEggFound(Base):
    __tablename__ = "easter_eggs_found"

    discord_id: Mapped[int] = mapped_column(BigInteger())
    easter_egg: Mapped[str] = mapped_column()

    __table_args__ = (PrimaryKeyConstraint(discord_id, easter_egg),)
