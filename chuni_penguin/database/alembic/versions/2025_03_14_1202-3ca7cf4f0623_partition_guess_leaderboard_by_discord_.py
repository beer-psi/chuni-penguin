"""partition guess leaderboard by discord IDs

Revision ID: 3ca7cf4f0623
Revises: d701d4d0c04b
Create Date: 2025-03-14 12:02:17.773948

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3ca7cf4f0623"
down_revision: Union[str, None] = "d701d4d0c04b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("guess_leaderboard", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "guild_id",
                sa.BigInteger(),
                server_default=sa.text("(-1)"),
                nullable=False,
            )
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    with op.batch_alter_table("guess_leaderboard", schema=None) as batch_op:
        batch_op.drop_column("guild_id")
    # ### end Alembic commands ###
