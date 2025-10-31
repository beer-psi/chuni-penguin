from typing import Optional

from discord.ext import commands
from discord.utils import escape_markdown
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    attribute_keyed_dict,
    mapped_column,
    relationship,
)

from chuni_penguin.networks.types import CourseClass
from chuni_penguin.utils import sdvxin_link


class Base(DeclarativeBase, AsyncAttrs):
    pass


class Cookie(Base):
    __tablename__ = "cookies"

    discord_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    cookie: Mapped[str] = mapped_column(String(64), nullable=False)
    kamaitachi_token: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


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

    jacket: Mapped[str] = mapped_column(nullable=False)

    available: Mapped[bool] = mapped_column(nullable=False)
    removed: Mapped[bool] = mapped_column(nullable=False)

    is_hidden_on_chuninet: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("FALSE")
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
        Index(
            "ix_aliases_lower_alias_guild_id",
            text("LOWER(alias)"),
            "guild_id",
            unique=True,
        ),
    )

    rowid: Mapped[int] = mapped_column(primary_key=True)

    alias: Mapped[str] = mapped_column(nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id: Mapped[Optional[int]] = mapped_column(BigInteger(), nullable=True)
    uses: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )

    song: Mapped["Song"] = relationship(back_populates="aliases")


class Prefix(Base):
    __tablename__ = "guild_prefix"

    guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    prefix: Mapped[str] = mapped_column(nullable=False)


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

    @hybrid_property
    def url(self) -> str:
        return sdvxin_link(self)


class GuessScore(Base):
    __tablename__ = "guess_leaderboard"
    __table_args__ = (
        Index("ix_guess_leaderboard_guild_id", "guild_id"),
        Index("ix_guess_leaderboard_guild_id_difficulty", "guild_id", "difficulty"),
        Index("ix_guess_leaderboard_guild_id_game_type", "guild_id", "game_type"),
        Index(
            "ix_guess_leaderboard_guild_id_difficulty_game_type",
            "guild_id",
            "difficulty",
            "game_type",
        ),
        UniqueConstraint(
            "discord_id",
            "guild_id",
            "difficulty",
            "game_type",
            name="_discord_id_guild_id_difficulty_game_type_uc",
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
    game_type: Mapped[str | None] = mapped_column(
        default=None, server_default=text("NULL")
    )
    score: Mapped[int] = mapped_column(nullable=False)


class UserConfig(Base):
    __tablename__ = "user_configs"
    __table_args__ = (Index("ix_user_configs_discord_id", "discord_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger(), unique=True)
    synthesis_alt_jacket: Mapped[str] = mapped_column()
    privacy_mode: Mapped[bool] = mapped_column(
        default=False, server_default=text("FALSE")
    )


class Denylist(Base):
    __tablename__ = "denylist"

    object_id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str | None] = mapped_column(
        default=None, server_default=text("NULL")
    )
    # TODO: We might want to have more granular controls in the future?

    def __repr__(self) -> str:
        return f"Denylist(object_id={self.object_id!r}, reason={self.reason!r})"


class EasterEggFound(Base):
    __tablename__ = "easter_eggs_found"

    discord_id: Mapped[int] = mapped_column(BigInteger())
    easter_egg: Mapped[str] = mapped_column()

    __table_args__ = (PrimaryKeyConstraint(discord_id, easter_egg),)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)

    cls: Mapped[CourseClass] = mapped_column()
    name: Mapped[str] = mapped_column()
    version: Mapped[str] = mapped_column()

    is_duplicate_track_allowed: Mapped[bool] = mapped_column()

    life: Mapped[int] = mapped_column()
    recovery_life: Mapped[int] = mapped_column()
    clear_life: Mapped[int] = mapped_column()
    damage_miss: Mapped[int] = mapped_column()
    damage_attack: Mapped[int] = mapped_column()
    damage_justice: Mapped[int] = mapped_column()
    damage_jcrit: Mapped[int] = mapped_column()

    tracks: Mapped[dict[int, "CourseTrack"]] = relationship(
        collection_class=attribute_keyed_dict("track"),
        back_populates="course",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Course(id={self.id!r}, cls={self.cls!r}, name={self.name!r}, version={self.version!r})"


course_track_charts: Table = Table(
    "course_track_charts",
    Base.metadata,
    Column(
        "course_id", ForeignKey("courses.id", ondelete="CASCADE", onupdate="CASCADE")
    ),
    Column("track", Integer()),
    Column(
        "song_id",
        ForeignKey("chunirec_songs.id", ondelete="CASCADE", onupdate="CASCADE"),
    ),
    Column("difficulty", String()),
    PrimaryKeyConstraint("course_id", "track", "song_id", "difficulty"),
    ForeignKeyConstraint(
        ["course_id", "track"],
        ["course_tracks.course_id", "course_tracks.track"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["song_id", "difficulty"],
        ["chunirec_charts.song_id", "chunirec_charts.difficulty"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),
)


class CourseTrack(Base):
    __tablename__ = "course_tracks"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE", onupdate="CASCADE")
    )
    track: Mapped[int] = mapped_column()

    level: Mapped[str | None] = mapped_column()

    charts: Mapped[list[Chart]] = relationship(secondary=course_track_charts)
    course: Mapped[Course] = relationship(back_populates="tracks")

    __table_args__ = (PrimaryKeyConstraint(course_id, track),)

    def __repr__(self) -> str:
        return f"CourseTrack(course_id={self.course_id!r}, track={self.track!r}, level={self.level!r})"
