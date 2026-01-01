"""Separate version and release date

Revision ID: f38b7c3d0930
Revises: 9eb37ded9579
Create Date: 2024-03-26 14:49:14.434017

"""

from datetime import datetime
from typing import Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f38b7c3d0930"
down_revision: Union[str, None] = "9eb37ded9579"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def release_to_chunithm_version(date: datetime) -> str:
    if (
        datetime(2015, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 1, 21, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM"
    if (
        datetime(2016, 2, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 7, 28, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM PLUS"
    if (
        datetime(2016, 8, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 1, 26, tzinfo=TOKYO_TZ)
    ):
        return "AIR"
    if (
        datetime(2017, 2, 9, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 8, 3, tzinfo=TOKYO_TZ)
    ):
        return "AIR PLUS"
    if (
        datetime(2017, 8, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 2, 22, tzinfo=TOKYO_TZ)
    ):
        return "STAR"
    if (
        datetime(2018, 3, 8, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 10, 11, tzinfo=TOKYO_TZ)
    ):
        return "STAR PLUS"
    if (
        datetime(2018, 10, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 3, 20, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON"
    if (
        datetime(2019, 4, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 10, 10, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON PLUS"
    if (
        datetime(2019, 10, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2020, 7, 2, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL"
    if (
        datetime(2020, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 1, 7, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL PLUS"
    if (
        datetime(2021, 1, 21, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 4, 28, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE"
    if (
        datetime(2021, 5, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 10, 21, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE LOST"
    if (
        datetime(2021, 11, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 4, 1, tzinfo=TOKYO_TZ)
    ):
        return "NEW"
    if (
        datetime(2022, 4, 14, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 9, 29, tzinfo=TOKYO_TZ)
    ):
        return "NEW PLUS"
    if (
        datetime(2022, 10, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 4, 27, tzinfo=TOKYO_TZ)
    ):
        return "SUN"
    if (
        datetime(2023, 5, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 11, 23, tzinfo=TOKYO_TZ)
    ):
        return "SUN PLUS"
    return "LUMINOUS"


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
