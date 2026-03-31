from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Character(Base):
    __tablename__: str = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    ages: Mapped[list[float] | None] = mapped_column(JSON(), nullable=True)
    age_text: Mapped[str] = mapped_column()
