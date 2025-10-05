"""Use a proper cookie jar

Revision ID: 50bb24f19a3a
Revises: 901af18ec932
Create Date: 2024-03-17 14:18:11.579871

"""

import io
from http.cookiejar import Cookie, LWPCookieJar
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50bb24f19a3a"
down_revision: Union[str, None] = "901af18ec932"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

cookies = sa.Table(
    "cookies",
    sa.MetaData(),
    sa.Column("discord_id", sa.BigInteger, primary_key=True),
    sa.Column("cookie", sa.String, nullable=False),
    sa.Column("kamaitachi_token", sa.String(40), nullable=True),
)


def upgrade() -> None:
    with op.batch_alter_table("cookies") as bop:
        bop.alter_column("cookie", type_=sa.String)

    conn = op.get_bind()
    rows = [x._asdict() for x in conn.execute(sa.select(cookies))]

    for row in rows:
        cookie = Cookie(
            version=0,
            name="clal",
            value=row["cookie"],
            port=None,
            port_specified=False,
            domain="lng-tgk-aime-gw.am-all.net",
            domain_specified=True,
            domain_initial_dot=False,
            path="/common_auth",
            path_specified=True,
            secure=False,
            expires=3856586927,  # 2092-03-17 10:08:47Z
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
        )
        jar = LWPCookieJar()
        jar.set_cookie(cookie)

        conn.execute(
            sa.update(cookies)
            .where(cookies.c.discord_id == row["discord_id"])
            .values(
                cookie=f"#LWP-Cookies-2.0\n{jar.as_lwp_str(ignore_discard=False, ignore_expires=False)}"
            )
        )

    conn.commit()


def downgrade() -> None:
    conn = op.get_bind()
    rows = [x._asdict() for x in conn.execute(sa.select(cookies))]

    for row in rows:
        if not row["cookie"].startswith("#LWP-Cookies-2.0"):
            continue

        jar = LWPCookieJar()

        jar._really_load(  # type: ignore[reportAttributeAccessIssue]
            io.StringIO(row["cookie"]),
            "?",
            ignore_discard=False,
            ignore_expires=False,
        )

        clal = None

        for cookie in jar:
            if (
                cookie.name == "clal"
                and cookie.domain == "lng-tgk-aime-gw.am-all.net"
                and cookie.path == "/common_auth"
            ):
                clal = cookie.value

        if clal is None:
            msg = f"Cookie jar for user ID {row['discord_id']} is missing the clal cookie."
            raise RuntimeError(msg)

        conn.execute(
            sa.update(cookies)
            .where(cookies.c.discord_id == row["discord_id"])
            .values(cookie=clal)
        )

    conn.commit()

    with op.batch_alter_table("cookies") as bop:
        bop.alter_column("cookie", type_=sa.String(64))
