"""convert level into string

Revision ID: 1e5d59ce579e
Revises: 50f211f12e75
Create Date: 2023-08-12 22:17:48.946733

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e5d59ce579e"
down_revision: Union[str, None] = "50f211f12e75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.alter_column(
            "level",
            existing_type=sa.REAL(),
            existing_nullable=False,
            type_=sa.VARCHAR(),
            nullable=False,
        )

    op.execute(
        """
        UPDATE chunirec_charts
        SET level = replace(replace(level, ".5", "+"), ".0", "")
        WHERE difficulty != "WE"
        """
    )

    op.execute(
        """
        UPDATE chunirec_charts
        SET level = replace(replace(chunirec_songs.title, rtrim(chunirec_songs.title, replace(chunirec_songs.title, '【', '')), ''), "】", ""),
            const = NULL
        FROM chunirec_songs
        WHERE chunirec_songs.id = chunirec_charts.song_id AND chunirec_charts.difficulty = "WE"
        """
    )

    op.execute(
        """
        UPDATE chunirec_songs
        SET title = rtrim(rtrim(title, replace(title, '【', '')), '【')
        WHERE chunithm_id >= 8000
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE chunirec_songs
        SET title = chunirec_songs.title || "【" || chunirec_charts.level || "】"
        FROM chunirec_charts
        WHERE chunirec_songs.id = chunirec_charts.song_id AND chunirec_charts.difficulty = "WE"
        """
    )

    op.execute(
        """
        UPDATE chunirec_charts
        SET level = 0.0, const = 0.0
        WHERE chunirec_charts.difficulty = "WE"
        """
    )

    op.execute(
        """
        UPDATE chunirec_charts
        SET level = CASE
                        WHEN level like '%+' THEN replace(level, "+", ".5")
                        ELSE level || ".0"
                    END
        WHERE difficulty != "WE"
        """
    )

    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.alter_column(
            "level",
            existing_type=sa.VARCHAR(),
            existing_nullable=False,
            type_=sa.REAL(),
            nullable=False,
        )
