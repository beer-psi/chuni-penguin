import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, Generic, TypeVar, override

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


class AsyncRcContextManager(contextlib.AbstractAsyncContextManager, Generic[T]):
    def __init__(
        self, inner: T, *, on_exit: list[Callable[[T], Awaitable[Any]]] | None = None
    ) -> None:
        super().__init__()

        self._inner = inner
        self._on_exit = on_exit or []

        self._lock = asyncio.Lock()
        self._refcount = 0

    @property
    def refcount(self) -> int:
        return self._refcount

    @property
    def inner(self) -> T:
        return self._inner

    @override
    async def __aenter__(self) -> T:
        async with self._lock:
            self._refcount += 1

        return self._inner

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ):
        async with self._lock:
            self._refcount -= 1

            if self._refcount == 0:
                for hook in self._on_exit:
                    await hook(self._inner)

                await self._inner.__aexit__(exc_type, exc_value, traceback)
