"""section off guess leaderboard by difficulty

Revision ID: aecb82bf47df
Revises: e8f3627eef6d
Create Date: 2025-03-14 21:06:47.157184

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aecb82bf47df"
down_revision: Union[str, None] = "e8f3627eef6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table(
        "guess_leaderboard", schema=None, recreate="always"
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "difficulty",
                sa.Integer(),
                nullable=False,
                default=-1,
                server_default=sa.text("-1"),
            ),
            insert_after="guild_id",
        )
        batch_op.drop_constraint("_discord_id_guild_id_uc", type_="unique")
        batch_op.create_unique_constraint(
            "_discord_id_guild_id_difficulty_uc",
            ["discord_id", "guild_id", "difficulty"],
        )


def downgrade() -> None:
    with op.batch_alter_table("guess_leaderboard", schema=None) as batch_op:
        batch_op.drop_constraint("_discord_id_guild_id_difficulty_uc", type_="unique")
        batch_op.create_unique_constraint(
            "_discord_id_guild_id_uc",
            ["discord_id", "guild_id"],
        )
        batch_op.drop_column("difficulty")
