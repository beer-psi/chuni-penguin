"""international_only

Another migration in the series of I Had To Do This Because CHUNITHM Has International
Exclusives. This flag in the song entry marks that the bot should use

    https://chunithm-net-eng.com/mobile/images/

instead of

    https://new.chunithm-net.com/chuni-mobile/html/mobile/img

for jacket URLs. It might do some other behavior in the future, if I bother to add support
for JP people.

Revision ID: 8cd5df7f3bb4
Revises: ac60aaf138a1
Create Date: 2023-09-28 23:06:08.860074

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8cd5df7f3bb4"
down_revision: Union[str, None] = "ac60aaf138a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "international_only",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.drop_column("international_only")
