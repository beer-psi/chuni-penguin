from typing import Optional

from discord.ext import commands
from discord.utils import escape_markdown
from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from .base import Base, UInt64Integer


class Song(Base):
    __tablename__ = "chunirec_songs"
    __table_args__ = (
        Index("ix_chunirec_songs_title", "title"),
        Index("ix_chunirec_songs_lower_title", text("LOWER(title)")),
        Index("ix_chunirec_songs_genre", "genre"),
        Index("ix_chunirec_songs_available", "available"),
        Index("ix_chunirec_songs_removed", "removed"),
        Index("ix_chunirec_songs_jacket", "jacket"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chunirec_id: Mapped[str | None] = mapped_column(
        nullable=True, default=None, server_default=text("NULL")
    )

    title: Mapped[str] = mapped_column(nullable=False)
    wikiwiki_title: Mapped[str | None] = mapped_column(
        nullable=True, default=None, server_default=text("NULL")
    )

    chunithm_catcode: Mapped[int] = mapped_column(nullable=False)
    genre: Mapped[str] = mapped_column(nullable=False)
    artist: Mapped[str] = mapped_column(nullable=False)

    version: Mapped[str] = mapped_column(nullable=False)
    release: Mapped[Optional[str]] = mapped_column(nullable=True)

    bpm: Mapped[Optional[int]] = mapped_column(nullable=True)
    min_bpm: Mapped[Optional[int]] = mapped_column(nullable=True)
    max_bpm: Mapped[Optional[int]] = mapped_column(nullable=True)

    jacket: Mapped[str | None] = mapped_column(nullable=True)

    available: Mapped[bool] = mapped_column(nullable=False)
    removed: Mapped[bool] = mapped_column(nullable=False)

    is_hidden_on_chuninet: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("FALSE")
    )
    duration: Mapped[int | None] = mapped_column(
        nullable=True, default=None, server_default=text("NULL")
    )

    charts: Mapped[list["Chart"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    aliases: Mapped[list["Alias"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    jackets: Mapped[list["SongJacket"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )

    def raise_if_not_available(self):
        if not self.available:
            if self.removed:
                msg = f"The song **{escape_markdown(self.title)}** is removed."
            else:
                msg = f"The song {escape_markdown(self.title)} is not available in CHUNITHM International."
            raise commands.CommandError(msg)

    def __repr__(self) -> str:
        return f"Song(id={self.id!r}, title={self.title!r})"


class SongJacket(Base):
    __tablename__ = "song_jackets"
    __table_args__ = (
        Index("ix_song_jackets_song_id", "song_id"),
        Index("ix_song_jackets_jacket_url", "jacket_url", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    jacket_url: Mapped[str] = mapped_column(nullable=False)

    song: Mapped["Song"] = relationship(back_populates="jackets")


class Chart(Base):
    __tablename__ = "chunirec_charts"
    __table_args__ = (
        Index("ix_chunirec_charts_song_id", "song_id"),
        Index("ix_chunirec_charts_difficulty", "difficulty"),
        Index("ix_chunirec_charts_level", "level"),
        Index("ix_chunirec_charts_const", "const"),
        Index(
            "ix_chunirec_charts_song_id_difficulty",
            "song_id",
            "difficulty",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
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
    available: Mapped[bool] = mapped_column(default=False, server_default=text("FALSE"))

    tachi_chart_id: Mapped[Optional[str]] = mapped_column(nullable=True)

    song: Mapped["Song"] = relationship(back_populates="charts")
    sdvxin_chart_view: Mapped[Optional["SdvxinChartView"]] = relationship(
        back_populates="chunithm_chart",
        primaryjoin="and_(Chart.song_id == SdvxinChartView.song_id, Chart.difficulty == SdvxinChartView.difficulty)",
    )

    def __repr__(self) -> str:
        return f"Chart(song_id={self.song_id!r}, difficulty={self.difficulty!r})"


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (
        Index("ix_aliases_alias", "alias"),
        Index("ix_aliases_guild_id", "guild_id"),
        Index("ix_aliases_lower_alias", text("LOWER(alias)")),
        Index("ix_aliases_song_id", "song_id"),
    )

    rowid: Mapped[int] = mapped_column(primary_key=True)

    alias: Mapped[str] = mapped_column(nullable=False)
    guild_id: Mapped[int] = mapped_column(UInt64Integer(), nullable=False)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[Optional[int]] = mapped_column(UInt64Integer(), nullable=True)
    uses: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )

    song: Mapped["Song"] = relationship(back_populates="aliases")


class SdvxinChartView(Base):
    __tablename__ = "sdvxin"
    __table_args__ = (
        Index("ix_sdvxin_song_id_difficulty", "song_id", "difficulty", unique=True),
        ForeignKeyConstraint(
            ["song_id", "difficulty"],
            ["chunirec_charts.song_id", "chunirec_charts.difficulty"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )

    rowid: Mapped[int] = mapped_column(primary_key=True)

    id: Mapped[str] = mapped_column(nullable=False)
    song_id: Mapped[int] = mapped_column(nullable=False)
    difficulty: Mapped[str] = mapped_column(nullable=False)
    end_index: Mapped[str] = mapped_column(nullable=False)

    chunithm_chart: Mapped["Chart"] = relationship(
        back_populates="sdvxin_chart_view",
        primaryjoin="and_(Chart.song_id == SdvxinChartView.song_id, Chart.difficulty == SdvxinChartView.difficulty)",
    )
