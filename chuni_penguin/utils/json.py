from typing import Any

import msgspec


def json_loads(s: str | bytes | bytearray):
    return msgspec.json.decode(s)


def json_dumps(obj: Any) -> str:
    return msgspec.json.encode(obj).decode("utf-8")
