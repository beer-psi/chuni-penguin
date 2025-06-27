import contextlib
from typing import TypeVar

T = TypeVar("T", bound=contextlib.AbstractAsyncContextManager)


class asuppress(contextlib.AbstractAsyncContextManager):
    def __init__(self, *exceptions) -> None:
        self._exceptions = exceptions

    async def __aenter__(self):
        pass

    # Pyright is stupid on this one.
    async def __aexit__(
        self,
        exctype: type[BaseException] | None,
        __exc_value,  # type: ignore[reportGeneralTypeIssues]
        __traceback,  # type: ignore[reportGeneralTypeIssues]
    ) -> bool | None:
        return exctype is not None and issubclass(exctype, self._exceptions)
