from typing import Generic, TypeVar, overload, override

KT = TypeVar("KT")
T = TypeVar("T")


class TypePairedDictKey(Generic[KT]):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    @override
    def __hash__(self) -> int:
        return self.name.__hash__()

    @override
    def __eq__(self, value: object, /) -> bool:
        return isinstance(value, TypePairedDictKey) and value.name == self.name


class TypePairedDict(dict):
    """
    A `dict` subclass that types values based on their keys. The intended usage is
    something like this:

    ```python
    # Keep the key as a constant, and optionally export it so consumers can also
    # get the stored value.
    KEY_SOMETHING = TypePairedDictKey[int]()

    data = TypePairedDict()
    reveal_type(data[KEY_SOMETHING])  # should be int
    ```
    """

    @override
    def __getitem__(self, key: TypePairedDictKey[KT]) -> KT:
        return super().__getitem__(key)

    @override
    def __setitem__(self, key: TypePairedDictKey[KT], value: KT) -> None:
        return super().__setitem__(key, value)

    @overload
    def get(self, key: TypePairedDictKey[KT]) -> KT | None: ...

    @overload
    def get(self, key: TypePairedDictKey[KT], default: KT) -> KT: ...

    @overload
    def get(self, key: TypePairedDictKey[KT], default: T) -> T | KT: ...

    @override
    def get(
        self, key: TypePairedDictKey[KT], default: T | KT | None = None
    ) -> T | KT | None:
        return super().get(key)
