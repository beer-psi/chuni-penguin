import asyncio
import contextlib
from typing import override

from cogs.gaming._session import GuessingGameSession

from .base import GuessingGameSkippableState, GuessingGameState
from .end_game import EndGameUserCanceled


class WaitState(GuessingGameSkippableState):
    def __init__(
        self,
        session: GuessingGameSession,
        wait_time_s: int,
        next_state: GuessingGameState,
    ):
        self.session = session
        self.wait_time_s = wait_time_s
        self.next_state = next_state

        self._task: asyncio.Task | None = None

    @override
    async def __call__(self) -> "GuessingGameState | None":
        self._task = asyncio.create_task(asyncio.sleep(self.wait_time_s))

        with contextlib.suppress(asyncio.CancelledError):
            await self._task

        if self.session.stopped_by:
            return EndGameUserCanceled(self.session)

        return self.next_state

    @override
    async def skip(self):
        if self._task is not None:
            self._task.cancel()
