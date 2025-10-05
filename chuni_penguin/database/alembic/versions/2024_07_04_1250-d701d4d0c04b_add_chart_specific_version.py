"""Add chart-specific version

Revision ID: d701d4d0c04b
Revises: 4b3abcf223b6
Create Date: 2024-07-04 12:50:23.449783

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d701d4d0c04b"
down_revision: Union[str, None] = "4b3abcf223b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_charts") as bop:
        bop.add_column(
            sa.Column("version", sa.String, nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("chunirec_charts") as bop:
        bop.drop_column("version")
