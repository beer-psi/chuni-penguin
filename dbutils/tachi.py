import httpx
import httpx_aiohttp
from sqlalchemy import bindparam, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import BoundLogger

from chuni_penguin.database import Chart


async def update_tachi(
    logger: BoundLogger, async_session: async_sessionmaker[AsyncSession]
):
    async with httpx.AsyncClient(
        transport=httpx_aiohttp.AIOHTTPTransport(retries=5)
    ) as client:
        resp = await client.get(
            "https://raw.githubusercontent.com/zkrising/Tachi/main/seeds/collections/charts-chunithm.json"
        )
        charts = resp.json()

    async with async_session() as session:
        stmt = (
            update(Chart)
            .where(
                (Chart.song_id == bindparam("b_song_id"))
                & (Chart.difficulty == bindparam("b_difficulty"))
            )
            .values(tachi_chart_id=bindparam("b_tachi_chart_id"))
        )
        connection = await session.connection()
        await connection.execute(
            stmt,
            [
                {
                    "b_song_id": c["data"]["inGameID"],
                    "b_difficulty": c["difficulty"][:3],
                    "b_tachi_chart_id": c["chartID"],
                }
                for c in charts
            ],
            execution_options={"synchronize_session": False},
        )
        await connection.commit()
