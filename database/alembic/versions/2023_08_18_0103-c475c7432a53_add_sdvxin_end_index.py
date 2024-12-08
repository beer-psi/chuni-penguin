"""add sdvxin.end_index

Some WORLD'S END songs have multiple versions. While they have different IDs in other
databases, they share the same ID in sdvx.in.
This column is used to distinguish it. The new sdvx.in URL for WORLD'S END will be
    "https://sdvx.in/chunithm/{difficulty}/{sdvxin_id}end{end_index or ''}.htm"

Revision ID: c475c7432a53
Revises: 63f40487528e
Create Date: 2023-08-18 01:03:03.781927

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c475c7432a53"
down_revision: Union[str, None] = "63f40487528e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sdvxin", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "end_index",
                sa.String(),
                server_default=sa.text("''"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("sdvxin", schema=None) as batch_op:
        batch_op.drop_column("end_index")
