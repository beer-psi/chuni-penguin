"""Separate version and release date

Revision ID: f38b7c3d0930
Revises: 9eb37ded9579
Create Date: 2024-03-26 14:49:14.434017

"""

from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from utils import TOKYO_TZ, release_to_chunithm_version

# revision identifiers, used by Alembic.
revision: str = "f38b7c3d0930"
down_revision: Union[str, None] = "9eb37ded9579"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


songs = sa.Table(
    "chunirec_songs",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True, nullable=False),
    sa.Column("release", sa.String, nullable=True),
    sa.Column("version", sa.String, nullable=False, server_default="Unknown"),
)


def upgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.alter_column("release", nullable=True)
        bop.add_column(
            sa.Column("version", sa.String, nullable=False, server_default="Unknown"),
            insert_after="release",
        )

    conn = op.get_bind()
    rows = [x._asdict() for x in conn.execute(sa.select(songs))]

    for row in rows:
        if row["release"] is not None:
            release = datetime.strptime(row["release"], "%Y-%m-%d").astimezone(TOKYO_TZ)
            version = release_to_chunithm_version(release)

            conn.execute(
                sa.update(songs).where(songs.c.id == row["id"]).values(version=version)
            )

    conn.commit()


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.alter_column("release", nullable=False)
        bop.drop_column("version")
