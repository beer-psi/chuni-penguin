import asyncio
import contextlib
from collections.abc import (
    Awaitable,
    Callable,
    ItemsView,
    Iterator,
    KeysView,
    Mapping,
    MutableMapping,
    ValuesView,
)
from types import TracebackType
from typing import Any, Generic, Self, TypeVar, override

T = TypeVar("T", bound=contextlib.AbstractAsyncContextManager)
KT = TypeVar("KT")
VT = TypeVar("VT")

MISSING: Any = object()


class AsyncRWLock:
    def __init__(self) -> None:
        self._cond: asyncio.Condition = asyncio.Condition()
        self._readers_active: int = 0
        self._writers_waiting: int = 0
        self._writer_active: bool = False

    async def read_acquire(self):
        async with self._cond:
            while self._writers_waiting > 0 or self._writer_active:
                _ = await self._cond.wait()

            self._readers_active += 1

    async def read_release(self):
        async with self._cond:
            self._readers_active -= 1

            if self._readers_active == 0:
                self._cond.notify_all()

    async def write_acquire(self):
        async with self._cond:
            self._writers_waiting += 1

            while self._readers_active > 0 or self._writer_active:
                _ = await self._cond.wait()

            self._writers_waiting -= 1
            self._writer_active = True

    async def write_release(self):
        async with self._cond:
            self._writer_active = False
            self._cond.notify_all()

    @contextlib.asynccontextmanager
    async def read(self):
        try:
            await self.read_acquire()
            yield
        finally:
            await self.read_release()

    @contextlib.asynccontextmanager
    async def write(self):
        try:
            await self.write_acquire()
            yield
        finally:
            await self.write_release()


class AsyncRWLockMappingReadGuard(
    Mapping[KT, VT], contextlib.AbstractAsyncContextManager
):
    def __init__(self, lock: AsyncRWLock, inner: dict[KT, VT]):
        self._lock = lock.read()
        self._locked: bool = False
        self._inner = inner

    def _ensure_locked(self):
        if not self._locked:
            msg = "not locked before access"
            raise RuntimeError(msg)

    @override
    async def __aenter__(self) -> Self:
        await self._lock.__aenter__()
        self._locked = True
        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ):
        await self._lock.__aexit__(exc_type, exc_value, traceback)
        self._locked = False

    @override
    def __iter__(self) -> Iterator[KT]:
        self._ensure_locked()
        return self._inner.__iter__()

    @override
    def __len__(self) -> int:
        self._ensure_locked()
        return self._inner.__len__()

    @override
    def __getitem__(self, key: KT, /) -> VT:
        self._ensure_locked()
        return self._inner[key]

    @override
    def items(self) -> ItemsView[KT, VT]:
        self._ensure_locked()
        return self._inner.items()

    @override
    def keys(self) -> KeysView[KT]:
        self._ensure_locked()
        return self._inner.keys()

    @override
    def values(self) -> ValuesView[VT]:
        self._ensure_locked()
        return self._inner.values()

    @override
    def __contains__(self, key: object, /) -> bool:
        self._ensure_locked()
        return self._inner.__contains__(key)

    @override
    def __eq__(self, other: object, /) -> bool:
        self._ensure_locked()

        if isinstance(
            other, (AsyncRWLockMappingReadGuard, AsyncRWLockMappingWriteGuard)
        ):
            other._ensure_locked()
            return self._inner.__eq__(other._inner)

        return self._inner.__eq__(other)


class AsyncRWLockMappingWriteGuard(
    AsyncRWLockMappingReadGuard[KT, VT], MutableMapping[KT, VT]
):
    def __init__(self, lock: AsyncRWLock, inner: dict[KT, VT]):
        self._lock = lock.write()
        self._locked: bool = False
        self._inner = inner

    @override
    def __setitem__(self, key: KT, value: VT, /) -> None:
        self._ensure_locked()
        return self._inner.__setitem__(key, value)

    @override
    def __delitem__(self, key: KT, /) -> None:
        self._ensure_locked()
        return self._inner.__delitem__(key)

    @override
    def clear(self) -> None:
        self._ensure_locked()
        return self._inner.clear()

    @override
    def pop(self, key: KT, /, default: T | VT = MISSING) -> T | VT:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._ensure_locked()

        if default is MISSING:
            return self._inner.pop(key)

        return self._inner.pop(key, default)

    @override
    def popitem(self) -> tuple[KT, VT]:
        self._ensure_locked()
        return self._inner.popitem()

    @override
    def setdefault(self, key: KT, default: T | None = None, /) -> T | None:  # pyright: ignore[reportIncompatibleMethodOverride, reportInconsistentOverload]
        self._ensure_locked()
        return self._inner.setdefault(key, default)  # pyright: ignore[reportArgumentType, reportReturnType]

    @override
    def update(self, mapping_or_iterable=MISSING, /, **kwargs):
        if mapping_or_iterable is not MISSING:
            return self.update(mapping_or_iterable, **kwargs)

        return self.update(**kwargs)


class AsyncRWLockMapping(Generic[KT, VT]):
    def __init__(self):
        self._lock: AsyncRWLock = AsyncRWLock()
        self._inner: dict[KT, VT] = {}

    def read(self):
        return AsyncRWLockMappingReadGuard(self._lock, self._inner)

    def write(self):
        return AsyncRWLockMappingWriteGuard(self._lock, self._inner)


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

            if self._refcount != 0:
                return

        for hook in self._on_exit:
            await hook(self._inner)

        await self._inner.__aexit__(exc_type, exc_value, traceback)
