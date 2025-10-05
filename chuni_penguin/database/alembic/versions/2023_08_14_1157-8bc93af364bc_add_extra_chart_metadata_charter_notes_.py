"""Add extra chart metadata (charter, notes by type, etc)

Revision ID: 8bc93af364bc
Revises: 1e5d59ce579e
Create Date: 2023-08-14 11:57:29.990351

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8bc93af364bc"
down_revision: Union[str, None] = "1e5d59ce579e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOTE_TYPES = ["tap", "hold", "slide", "air", "flick"]


def upgrade() -> None:
    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        for note_type in NOTE_TYPES:
            batch_op.add_column(
                sa.Column(note_type, sa.Integer(), nullable=True),
            )
        batch_op.add_column(
            sa.Column("charter", sa.String(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.drop_column("charter")
        for note_type in NOTE_TYPES:
            batch_op.drop_column(note_type)
