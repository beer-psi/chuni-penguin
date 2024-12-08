"""make bpm nullable

Revision ID: 50f211f12e75
Revises: e6d4f33f73d6
Create Date: 2023-08-12 15:09:54.538846

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50f211f12e75"
down_revision: Union[str, None] = "e6d4f33f73d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    songs = sa.sql.table(
        "chunirec_songs",
        sa.Column("bpm", sa.INTEGER(), nullable=True),
        schema=None,
    )

    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.alter_column(
            "bpm",
            existing_type=sa.INTEGER(),
            existing_nullable=False,
            nullable=True,
        )

    op.execute(songs.update().where(songs.c.bpm == 0).values(bpm=None))


def downgrade() -> None:
    songs = sa.sql.table(
        "chunirec_songs",
        sa.Column("bpm", sa.INTEGER(), nullable=True),
        schema=None,
    )

    op.execute(songs.update().where(songs.c.bpm.is_(None)).values(bpm=0))

    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.alter_column(
            "bpm",
            existing_type=sa.INTEGER(),
            existing_nullable=True,
            nullable=False,
        )
