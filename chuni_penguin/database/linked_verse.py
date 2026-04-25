from datetime import datetime

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, DateTimeUTC
from .songs import Song


class LinkedGate(Base):
    __tablename__ = "linked_gates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    color: Mapped[str] = mapped_column()
    song_id: Mapped[int] = mapped_column(
        ForeignKey("chunirec_songs.id", onupdate="CASCADE", ondelete="CASCADE")
    )
    available: Mapped[bool] = mapped_column(default=False, server_default=text("FALSE"))
    open_condition: Mapped[str] = mapped_column()
    unlock_condition: Mapped[str] = mapped_column()

    song: Mapped[Song] = relationship()
    conditions: Mapped[list["LinkedGateCondition"]] = relationship()


class LinkedGateCondition(Base):
    __tablename__ = "linked_gate_conditions"

    linked_gate_id: Mapped[int] = mapped_column(
        ForeignKey("linked_gates.id", onupdate="CASCADE", ondelete="CASCADE")
    )
    level: Mapped[int] = mapped_column()
    region: Mapped[str] = mapped_column()

    difficulty: Mapped[str] = mapped_column()
    life: Mapped[int] = mapped_column()
    recovery_life: Mapped[int] = mapped_column()
    recovery_life_combo_type: Mapped[str] = mapped_column(
        default="combo", server_default=text("'combo'")
    )
    damage_miss: Mapped[int] = mapped_column()
    damage_attack: Mapped[int] = mapped_column()
    damage_justice: Mapped[int] = mapped_column()

    is_local_matching_required: Mapped[bool] = mapped_column(
        default=False, server_default=false()
    )
    survivors_required: Mapped[int | None] = mapped_column(
        default=None, server_default=text("NULL")
    )

    start_date: Mapped[datetime] = mapped_column(DateTimeUTC())
    end_date: Mapped[datetime | None] = mapped_column(DateTimeUTC())

    __table_args__ = (PrimaryKeyConstraint(linked_gate_id, level, region),)
