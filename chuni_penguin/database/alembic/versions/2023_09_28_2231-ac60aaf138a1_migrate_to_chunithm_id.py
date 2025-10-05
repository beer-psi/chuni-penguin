"""migrate to chunithm_id

Depending on chunirec has made fetching data for this bot simple, but it is also a pain
in the ass when CHUNITHM International ver. decide to drop an update that JP doesn't
have (yet). As a result, we are migrating away from using chunirec IDs altogether.

Wear your seatbelts, this is a primary key migration.

Revision ID: ac60aaf138a1
Revises: c475c7432a53
Create Date: 2023-09-28 22:31:41.775216

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac60aaf138a1"
down_revision: Union[str, None] = "c475c7432a53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("PRAGMA foreign_keys=OFF")

    op.execute(
        """
        UPDATE aliases
        SET song_id = chunirec_songs.chunithm_id
        FROM chunirec_songs
        WHERE chunirec_songs.id = aliases.song_id
        """
    )

    op.execute(
        """
        UPDATE sdvxin
        SET song_id = chunirec_songs.chunithm_id
        FROM chunirec_songs
        WHERE chunirec_songs.id = sdvxin.song_id
        """
    )

    op.execute(
        """
        UPDATE chunirec_charts
        SET song_id = chunirec_songs.chunithm_id
        FROM chunirec_songs
        WHERE chunirec_songs.id = chunirec_charts.song_id
        """
    )

    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.drop_column("id")
        batch_op.alter_column("chunithm_id", new_column_name="id")

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise Exception("There's no way back.")  # noqa: EM101, TRY002, TRY003
