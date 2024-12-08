"""add owner_id to aliases

Revision ID: e6d4f33f73d6
Revises: 88a887bd5d02
Create Date: 2023-08-12 13:23:11.156402

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6d4f33f73d6"
down_revision: Union[str, None] = "88a887bd5d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aliases",
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("aliases", schema=None) as batch_op:
        batch_op.drop_column("owner_id")
