"""Add available/removed flags to songs

Revision ID: 9eb37ded9579
Revises: 50bb24f19a3a
Create Date: 2024-03-17 17:22:59.319382

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9eb37ded9579"
down_revision: Union[str, None] = "50bb24f19a3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.add_column(
            sa.Column("available", sa.Integer, nullable=False, server_default="1")
        )
        bop.add_column(
            sa.Column("removed", sa.Integer, nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.drop_column("available")
        bop.drop_column("removed")
