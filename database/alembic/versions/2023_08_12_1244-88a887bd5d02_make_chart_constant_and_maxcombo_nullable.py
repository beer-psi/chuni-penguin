"""make chart constant and maxcombo nullable

Revision ID: 88a887bd5d02
Revises:
Create Date: 2023-08-12 12:44:33.418501

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "88a887bd5d02"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    charts = sa.sql.table(
        "chunirec_charts",
        sa.Column("const", sa.REAL(), nullable=False),
        sa.Column("maxcombo", sa.INTEGER(), nullable=False),
        sa.Column("is_const_unknown", sa.BOOLEAN(), nullable=False),
        schema=None,
    )

    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.alter_column(
            "const",
            existing_type=sa.REAL(),
            existing_nullable=False,
            nullable=True,
        )

        batch_op.alter_column(
            "maxcombo",
            existing_type=sa.INTEGER(),
            existing_nullable=False,
            nullable=True,
        )

    op.execute(
        # SQL doesn't work like python, ignore E712
        charts.update()
        .where(charts.c.is_const_unknown == True)  # noqa: E712
        .values(const=None)
    )

    op.execute(charts.update().where(charts.c.maxcombo == 0).values(maxcombo=None))

    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.drop_column("is_const_unknown")


def downgrade() -> None:
    charts = sa.sql.table(
        "chunirec_charts",
        sa.Column("const", sa.REAL(), nullable=True),
        sa.Column("maxcombo", sa.INTEGER(), nullable=True),
        schema=None,
    )

    op.add_column(
        "chunirec_charts",
        sa.Column("is_const_unknown", sa.BOOLEAN(), nullable=False),
    )

    op.execute(charts.update().where(charts.c.maxcombo.is_(None)).values(maxcombo=0))

    op.execute(
        charts.update()
        .where(charts.c.const.is_(None))
        .values(const=0, is_const_unknown=True)
    )

    with op.batch_alter_table("chunirec_charts", schema=None) as batch_op:
        batch_op.alter_column(
            "maxcombo",
            existing_type=sa.INTEGER(),
            existing_nullable=True,
            nullable=False,
        )

        batch_op.alter_column(
            "const",
            existing_type=sa.REAL(),
            existing_nullable=True,
            nullable=False,
        )
