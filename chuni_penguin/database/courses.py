from sqlalchemy import (
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
)
from sqlalchemy.orm import (
    Mapped,
    attribute_keyed_dict,
    mapped_column,
    relationship,
)

from chuni_penguin.networks.types import CourseClass

from .base import Base
from .songs import Chart


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
