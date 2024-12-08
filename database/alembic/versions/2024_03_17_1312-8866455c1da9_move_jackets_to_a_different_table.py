"""Move jackets to a different table

Revision ID: 8866455c1da9
Revises: 8cd5df7f3bb4
Create Date: 2024-03-17 13:12:52.186521

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from chunithm_net.consts import INTERNATIONAL_JACKET_BASE, JACKET_BASE

# revision identifiers, used by Alembic.
revision: str = "8866455c1da9"
down_revision: Union[str, None] = "8cd5df7f3bb4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

metadata = sa.MetaData()
songs = sa.Table(
    "chunirec_songs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("jacket", sa.String),
    sa.Column("zetaraku_jacket", sa.String),
)
song_jackets = sa.Table(
    "song_jackets",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column(
        "song_id",
        sa.ForeignKey("chunirec_songs.id", ondelete="cascade", onupdate="cascade"),
        nullable=False,
    ),
    sa.Column("jacket_url", sa.String, nullable=False),
    sa.UniqueConstraint("jacket_url"),
)


def upgrade() -> None:
    op.create_table(
        "song_jackets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("song_id", sa.Integer, nullable=False),
        sa.Column("jacket_url", sa.String, nullable=False),
    )

    with op.batch_alter_table("song_jackets") as bop:
        bop.create_foreign_key(
            "fk_chunirec_songs_id",
            "chunirec_songs",
            ["song_id"],
            ["song"],
            ondelete="cascade",
            onupdate="cascade",
        )
        bop.create_unique_constraint("uq_song_jackets_jacket_url", ["jacket_url"])

    connection = op.get_bind()
    rows = connection.execute(sa.select(songs))
    inserted_rows = []

    for row in rows:
        row_dict = row._asdict()
        inserted_rows.append(
            {
                "song_id": row_dict["id"],
                "jacket_url": f"{INTERNATIONAL_JACKET_BASE}/{row_dict['jacket']}",
            },
        )
        inserted_rows.append(
            {
                "song_id": row_dict["id"],
                "jacket_url": f"{JACKET_BASE}/{row_dict['jacket']}",
            }
        )

        if (zetaraku := row_dict.get("zetaraku_jacket")) is not None:
            inserted_rows.append(
                {
                    "song_id": row_dict["id"],
                    "jacket_url": f"https://dp4p6x0xfi5o9.cloudfront.net/chunithm/img/cover/{zetaraku}",
                }
            )

    connection.execute(sa.insert(song_jackets).values(inserted_rows))

    with op.batch_alter_table("chunirec_songs") as bop:
        bop.drop_column("zetaraku_jacket")


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs") as bop:
        bop.add_column(
            sa.Column("zetaraku_jacket", sa.String),
        )

    connection = op.get_bind()
    rows = [x._asdict() for x in connection.execute(sa.select(song_jackets))]
    for row in rows:
        if not row["jacket_url"].startswith(
            "https://dp4p6x0xfi5o9.cloudfront.net/chunithm/img/cover/"
        ):
            continue
        filename = row["jacket_url"].split("/")[-1]
        sql = (
            sa.update(songs)
            .where(songs.c.id == row["song_id"])
            .values(zetaraku_jacket=filename)
        )
        connection.execute(sql)

    connection.commit()

    op.drop_table("song_jackets")
