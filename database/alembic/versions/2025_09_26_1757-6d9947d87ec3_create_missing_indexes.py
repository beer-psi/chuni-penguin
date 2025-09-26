"""create missing indexes

Revision ID: 6d9947d87ec3
Revises: be44dbe4b4bf
Create Date: 2025-09-26 17:57:19.639354

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d9947d87ec3"
down_revision: Union[str, None] = "be44dbe4b4bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_aliases_lower_alias ON aliases (LOWER(alias))"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_aliases_lower_alias_guild_id ON aliases (LOWER(alias), guild_id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("aliases", schema=None) as batch_op:
        batch_op.drop_index("ix_aliases_lower_alias")
        batch_op.drop_index("ix_aliases_lower_alias_guild_id")
