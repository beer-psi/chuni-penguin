"""min_bpm and max_bpm

Revision ID: 4b3abcf223b6
Revises: 4d22bfbbe8a9
Create Date: 2024-05-15 07:51:41.758813

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b3abcf223b6"
down_revision: Union[str, None] = "4d22bfbbe8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_songs", recreate="always") as bop:
        bop.add_column(
            sa.Column("min_bpm", sa.Integer, nullable=True),
            insert_after="bpm",
        )
        bop.add_column(
            sa.Column("max_bpm", sa.Integer, nullable=True),
            insert_after="min_bpm",
        )


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.drop_column("min_bpm")
        bop.drop_column("max_bpm")
