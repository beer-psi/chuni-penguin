from typing import Optional

from discord.ext import commands
from rapidfuzz import fuzz
from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
    type_coerce,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from utils import sdvxin_link


class Base(DeclarativeBase, AsyncAttrs):
    pass


class Cookie(Base):
    __tablename__ = "cookies"

    discord_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    cookie: Mapped[str] = mapped_column(String(64), nullable=False)
    kamaitachi_token: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class Song(Base):
    __tablename__ = "chunirec_songs"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(nullable=False)

    chunithm_catcode: Mapped[int] = mapped_column(nullable=False)
    genre: Mapped[str] = mapped_column(nullable=False)
    artist: Mapped[str] = mapped_column(nullable=False)

    version: Mapped[str] = mapped_column(nullable=False)
    release: Mapped[Optional[str]] = mapped_column(nullable=True)

    bpm: Mapped[Optional[int]] = mapped_column(nullable=True)
    min_bpm: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_bpm: Mapped[Optional[int]] = mapped_column(nullable=True)

    jacket: Mapped[str] = mapped_column(nullable=False)

    available: Mapped[bool] = mapped_column(nullable=False)
    removed: Mapped[bool] = mapped_column(nullable=False)

    charts: Mapped[list["Chart"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    aliases: Mapped[list["Alias"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    jackets: Mapped[list["SongJacket"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )

    @hybrid_method
    def similarity(self, search: str) -> float:
        return fuzz.QRatio(search, self.title, processor=str.lower)

    @similarity.inplace.expression
    @classmethod
    def _similarity_expr(cls, search: str) -> ColumnElement[float]:
        return type_coerce(func.fuzz_qratio(search, cls.title), Float)

    def raise_if_not_available(self):
        if not self.available:
            if self.removed:
                msg = f"The song {self.title} is removed."
            else:
                msg = (
                    f"The song {self.title} is not available in CHUNITHM International."
                )
            raise commands.BadArgument(msg)


class SongJacket(Base):
    __tablename__ = "song_jackets"
    __table_args__ = (UniqueConstraint("jacket_url", name="_jacket_url_uc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id"), nullable=False
    )
    jacket_url: Mapped[str] = mapped_column(nullable=False)

    song: Mapped["Song"] = relationship(back_populates="jackets")


class Chart(Base):
    __tablename__ = "chunirec_charts"
    __table_args__ = (
        UniqueConstraint("song_id", "difficulty", name="_song_id_difficulty_uc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id"), nullable=False
    )

    difficulty: Mapped[str] = mapped_column(nullable=False)
    level: Mapped[str] = mapped_column(nullable=False)
    const: Mapped[Optional[float]] = mapped_column(nullable=True)

    maxcombo: Mapped[Optional[int]] = mapped_column(nullable=True)
    tap: Mapped[Optional[int]] = mapped_column(nullable=True)
    hold: Mapped[Optional[int]] = mapped_column(nullable=True)
    slide: Mapped[Optional[int]] = mapped_column(nullable=True)
    air: Mapped[Optional[int]] = mapped_column(nullable=True)
    flick: Mapped[Optional[int]] = mapped_column(nullable=True)

    charter: Mapped[Optional[str]] = mapped_column(nullable=True)
    version: Mapped[Optional[str]] = mapped_column(nullable=True)

    song: Mapped["Song"] = relationship(back_populates="charts")
    sdvxin_chart_view: Mapped[Optional["SdvxinChartView"]] = relationship(
        back_populates="chunithm_chart",
        primaryjoin="and_(Chart.song_id == SdvxinChartView.song_id, Chart.difficulty == SdvxinChartView.difficulty)",
    )


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("alias", "guild_id", name="_alias_guild_id_uc"),)

    rowid: Mapped[int] = mapped_column(primary_key=True)

    alias: Mapped[str] = mapped_column(nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id"), nullable=False
    )
    owner_id: Mapped[Optional[int]] = mapped_column(BigInteger(), nullable=True)

    song: Mapped["Song"] = relationship(back_populates="aliases")

    @hybrid_method
    def similarity(self, search: str) -> float:
        return fuzz.QRatio(search, self.alias, processor=str.lower)

    @similarity.inplace.expression
    @classmethod
    def _similarity_expr(cls, search: str) -> ColumnElement[float]:
        return type_coerce(func.fuzz_qratio(search, cls.alias), Float)


class Prefix(Base):
    __tablename__ = "guild_prefix"

    guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    prefix: Mapped[str] = mapped_column(nullable=False)


class SdvxinChartView(Base):
    __tablename__ = "sdvxin"
    __table_args__ = (UniqueConstraint("id", "difficulty", name="_id_difficulty_uc"),)

    rowid: Mapped[int] = mapped_column(primary_key=True)

    id: Mapped[str] = mapped_column(nullable=False)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_charts.song_id"), nullable=False
    )
    difficulty: Mapped[str] = mapped_column(
        ForeignKey("chunirec_charts.difficulty"), nullable=False
    )
    end_index: Mapped[str] = mapped_column(nullable=False)

    chunithm_chart: Mapped["Chart"] = relationship(
        back_populates="sdvxin_chart_view",
        primaryjoin="and_(Chart.song_id == SdvxinChartView.song_id, Chart.difficulty == SdvxinChartView.difficulty)",
    )

    @hybrid_property
    def url(self) -> str:
        return sdvxin_link(self)


class GuessScore(Base):
    __tablename__ = "guess_leaderboard"
    __table_args__ = (
        UniqueConstraint(
            "discord_id",
            "guild_id",
            "difficulty",
            name="_discord_id_guild_id_difficulty_uc",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger())
    guild_id: Mapped[int] = mapped_column(
        BigInteger(), nullable=False, default=-1, server_default=text("-1")
    )
    difficulty: Mapped[int] = mapped_column(
        nullable=False, default=-1, server_default=text("-1")
    )
    score: Mapped[int] = mapped_column(nullable=False)
