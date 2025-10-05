"""Fixing fucked up song_jackets migration

Revision ID: 4d22bfbbe8a9
Revises: f38b7c3d0930
Create Date: 2024-03-26 16:23:18.667950

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d22bfbbe8a9"
down_revision: Union[str, None] = "f38b7c3d0930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("song_jackets") as bop:
        bop.drop_constraint("fk_chunirec_songs_id")
        bop.create_foreign_key(
            "fk_chunirec_songs_id",
            "chunirec_songs",
            ["song_id"],
            ["id"],
            ondelete="cascade",
            onupdate="cascade",
        )


def downgrade() -> None:
    with op.batch_alter_table("song_jackets") as bop:
        bop.drop_constraint("fk_chunirec_songs_id")
        bop.create_foreign_key(
            "fk_chunirec_songs_id",
            "chunirec_songs",
            ["song_id"],
            ["song"],
            ondelete="cascade",
            onupdate="cascade",
        )
