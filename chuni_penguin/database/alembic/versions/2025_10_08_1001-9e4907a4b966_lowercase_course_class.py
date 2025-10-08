"""lowercase course class

Revision ID: 9e4907a4b966
Revises: 75ed42605cb2
Create Date: 2025-10-08 10:01:42.899172

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e4907a4b966"
down_revision: Union[str, None] = "75ed42605cb2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE courses SET cls = LOWER(cls)")


def downgrade() -> None:
    op.execute("UPDATE courses SET cls = UPPER(cls)")
