"""fix -1 in uint64

Revision ID: 304e2e43729c
Revises: 6d34ec73965f
Create Date: 2026-01-13 08:53:55.846533

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "304e2e43729c"
down_revision: Union[str, None] = "6d34ec73965f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE aliases SET guild_id = 0 WHERE guild_id = -1")


def downgrade() -> None:
    op.execute("UPDATE aliases SET guild_id = -1 WHERE guild_id = 0")
