from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UInt64Integer


class Prefix(Base):
    __tablename__ = "guild_prefix"

    guild_id: Mapped[int] = mapped_column(UInt64Integer(), primary_key=True)
    prefix: Mapped[str] = mapped_column(nullable=False)
