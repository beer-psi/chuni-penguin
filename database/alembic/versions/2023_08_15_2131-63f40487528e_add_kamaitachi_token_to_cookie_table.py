"""Add kamaitachi_token to Cookie table

Revision ID: 63f40487528e
Revises: 8bc93af364bc
Create Date: 2023-08-15 21:31:34.611486

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "63f40487528e"
down_revision: Union[str, None] = "8bc93af364bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cookies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kamaitachi_token", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("cookies", schema=None) as batch_op:
        batch_op.drop_column("kamaitachi_token")
