"""All songs are international

Revision ID: 901af18ec932
Revises: 8866455c1da9
Create Date: 2024-03-17 13:43:04.158630

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "901af18ec932"
down_revision: Union[str, None] = "8866455c1da9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.drop_column("international_only")


def downgrade() -> None:
    with op.batch_alter_table("chunirec_songs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "international_only",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )
