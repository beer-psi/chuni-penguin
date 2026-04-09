from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from chuni_penguin.types import ClearLamp, ComboLamp

from .base import Base, UInt64Integer


class PersonalBest(Base):
    __tablename__ = "personal_bests"

    discord_id: Mapped[int] = mapped_column(UInt64Integer())
    network: Mapped[str] = mapped_column()
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    difficulty: Mapped[str] = mapped_column()

    score: Mapped[int] = mapped_column()

    justice_heaven: Mapped[int | None] = mapped_column()
    justice_critical: Mapped[int | None] = mapped_column()
    justice: Mapped[int | None] = mapped_column()
    attack: Mapped[int | None] = mapped_column()
    miss: Mapped[int | None] = mapped_column()

    max_combo: Mapped[int | None] = mapped_column()

    clear_lamp: Mapped[int] = mapped_column(
        default=ClearLamp.failed.value, server_default=text(f"{ClearLamp.failed.value}")
    )
    combo_lamp: Mapped[int] = mapped_column(
        default=ComboLamp.none.value, server_default=text(f"{ComboLamp.none.value}")
    )
    chain_lamp: Mapped[int | None] = mapped_column(
        default=None, server_default=text("NULL")
    )

    achieved_at: Mapped[datetime | None] = mapped_column()
    last_played_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        PrimaryKeyConstraint(discord_id, network, song_id, difficulty),
        ForeignKeyConstraint(
            [song_id, difficulty],
            ["chunirec_charts.song_id", "chunirec_charts.difficulty"],
            name="fk_personal_bests_song_id_difficulty_chunirec_charts",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        Index("ix_personal_bests_discord_id", discord_id),
        Index("ix_personal_bests_discord_id_song_id", discord_id, song_id),
        Index(
            "ix_personal_bests_discord_id_song_id_difficulty",
            discord_id,
            song_id,
            difficulty,
        ),
    )

    def __repr__(self) -> str:
        discord_id = self.discord_id
        network = self.network
        song_id = self.song_id
        difficulty = self.difficulty
        score = self.score
        achieved_at = self.achieved_at
        last_played_at = self.last_played_at

        return f"{self.__class__.__name__}({discord_id=}, {network=}, {song_id=}, {difficulty=}, {score=}, {achieved_at=}, {last_played_at=})"
