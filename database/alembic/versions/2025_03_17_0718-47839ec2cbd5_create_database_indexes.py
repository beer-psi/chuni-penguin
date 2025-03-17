"""create database indexes

Revision ID: 47839ec2cbd5
Revises: aecb82bf47df
Create Date: 2025-03-17 07:18:30.917434

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "47839ec2cbd5"
down_revision: Union[str, None] = "aecb82bf47df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

conventions = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_`%(constraint_name)s`",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "aliases", schema=None, naming_convention=conventions
    ) as batch_op:
        batch_op.drop_constraint("uq_aliases_alias", type_="unique")

    # Deduplicate any aliases that are duplicates in lowercase
    op.execute("""DELETE FROM aliases WHERE rowid || LOWER(alias) || guild_id NOT IN (
        SELECT rowid || LOWER(alias) || guild_id
        FROM aliases
        GROUP BY LOWER(alias)
    )
    """)
    op.execute("""CREATE UNIQUE INDEX ix_aliases_lower_alias_guild_id
    ON aliases (LOWER(alias), guild_id)
    """)


def downgrade() -> None:
    with op.batch_alter_table(
        "aliases", schema=None, naming_convention=conventions
    ) as batch_op:
        batch_op.drop_index("ix_aliases_lower_alias_guild_id")
        batch_op.create_unique_constraint("uq_aliases_alias", ["alias", "guild_id"])
