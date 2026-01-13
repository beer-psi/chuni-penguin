from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UInt64Integer


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
    discord_id: Mapped[int] = mapped_column(UInt64Integer())
    guild_id: Mapped[int] = mapped_column(
        UInt64Integer(), nullable=False, default=0, server_default=text("0")
    )
    difficulty: Mapped[int] = mapped_column(
        nullable=False, default=-1, server_default=text("-1")
    )
    game_type: Mapped[str | None] = mapped_column(
        default=None, server_default=text("NULL")
    )
    score: Mapped[int] = mapped_column(nullable=False)
