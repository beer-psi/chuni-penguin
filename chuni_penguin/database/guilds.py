from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Prefix(Base):
    __tablename__ = "guild_prefix"

    guild_id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    prefix: Mapped[str] = mapped_column(nullable=False)
