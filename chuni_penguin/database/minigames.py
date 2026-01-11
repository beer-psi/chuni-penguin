from sqlalchemy import BigInteger, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
