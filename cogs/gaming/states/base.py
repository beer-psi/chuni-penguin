from typing import Protocol


class GuessingGameState(Protocol):
    async def __call__(self) -> "GuessingGameState | None":
        """Execute the current state.

        It must return another state for the executor to run, or return None
        to finish the state machine.
        """
        ...


class GuessingGameSkippableState(GuessingGameState):
    async def skip(self):
        """Skips the current state."""
