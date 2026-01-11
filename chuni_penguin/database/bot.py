from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Denylist(Base):
    __tablename__ = "denylist"

    object_id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str | None] = mapped_column(
        default=None, server_default=text("NULL")
    )
    # TODO: We might want to have more granular controls in the future?

    def __repr__(self) -> str:
        return f"Denylist(object_id={self.object_id!r}, reason={self.reason!r})"
