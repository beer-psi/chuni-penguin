from typing import Generic, TypeVar, overload

KT = TypeVar("KT")
T = TypeVar("T")


class TypePairedDictKey(Generic[KT]):
    pass


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

    def __getitem__(self, key: TypePairedDictKey[KT]) -> KT:
        return super().__getitem__(key)

    def __setitem__(self, key: TypePairedDictKey[KT], value: KT) -> None:
        return super().__setitem__(key, value)

    @overload
    def get(self, key: TypePairedDictKey[KT]) -> KT | None: ...

    @overload
    def get(self, key: TypePairedDictKey[KT], default: KT) -> KT: ...

    @overload
    def get(self, key: TypePairedDictKey[KT], default: T) -> T | KT: ...

    def get(
        self, key: TypePairedDictKey[KT], default: T | KT | None = None
    ) -> T | KT | None:
        return super().get(key)
