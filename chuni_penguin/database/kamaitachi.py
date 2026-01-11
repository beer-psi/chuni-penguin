from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PendingKamaitachiImport(Base):
    __tablename__ = "pending_kamaitachi_imports"
    __table_args__ = (Index("ix_pending_kamaitachi_imports_discord_id", "discord_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger())
    import_data: Mapped[dict[str, Any]] = mapped_column(JSON())
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP"),
    )
