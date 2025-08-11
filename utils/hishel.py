from datetime import datetime
from typing import Any, override

import hishel
import httpcore
import msgspec
from hishel._serializers import (
    KNOWN_REQUEST_EXTENSIONS,
    KNOWN_RESPONSE_EXTENSIONS,
    Metadata,
)
from hishel._utils import normalized_url


class HishelCachedRequest(msgspec.Struct):
    method: bytes = msgspec.field(name="m")
    url: str = msgspec.field(name="u")
    headers: list[tuple[bytes, bytes]] = msgspec.field(name="h")
    extensions: dict[str, Any] = msgspec.field(name="e")


class HishelCachedResponse(msgspec.Struct):
    status: int = msgspec.field(name="s")
    headers: list[tuple[bytes, bytes]] = msgspec.field(name="h")
    content: bytes = msgspec.field(name="c")
    extensions: dict[str, bytes] = msgspec.field(name="e")


class HishelCacheMetadata(msgspec.Struct):
    cache_key: str = msgspec.field(name="k")
    number_of_uses: int = msgspec.field(name="n")
    created_at: str = msgspec.field(name="t")


class HishelCacheEntry(msgspec.Struct):
    response: HishelCachedResponse = msgspec.field(name="r")
    request: HishelCachedRequest = msgspec.field(name="q")
    metadata: HishelCacheMetadata = msgspec.field(name="m")


class HishelMsgspecSerializer(hishel.BaseSerializer):
    @override
    def dumps(
        self,
        response: httpcore.Response,
        request: httpcore.Request,
        metadata: Metadata,
    ) -> str | bytes:
        return msgspec.msgpack.encode(
            HishelCacheEntry(
                response=HishelCachedResponse(
                    status=response.status,
                    headers=response.headers,
                    content=response.content,
                    extensions={
                        key: value
                        for key, value in response.extensions.items()
                        if key in KNOWN_RESPONSE_EXTENSIONS
                    },
                ),
                request=HishelCachedRequest(
                    method=request.method,
                    url=normalized_url(request.url),
                    headers=request.headers,
                    extensions={
                        key: value
                        for key, value in request.extensions.items()
                        if key in KNOWN_REQUEST_EXTENSIONS
                    },
                ),
                metadata=HishelCacheMetadata(
                    cache_key=metadata["cache_key"],
                    number_of_uses=metadata["number_of_uses"],
                    created_at=metadata["created_at"].strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    ),
                ),
            )
        )

    @override
    def loads(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, data: bytes
    ) -> tuple[httpcore.Response, httpcore.Request, hishel._serializers.Metadata]:
        full = msgspec.msgpack.decode(data, type=HishelCacheEntry)
        response_data = full.response
        request_data = full.request
        metadata = full.metadata

        response = httpcore.Response(
            status=response_data.status,
            headers=response_data.headers,
            content=response_data.content,
            extensions={
                key: value
                for key, value in response_data.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )

        request = httpcore.Request(
            method=request_data.method,
            url=request_data.url,
            headers=request_data.headers,
            extensions={
                key: value
                for key, value in request_data.extensions.items()
                if key in KNOWN_REQUEST_EXTENSIONS
            },
        )

        return (
            response,
            request,
            {
                "cache_key": metadata.cache_key,
                "created_at": datetime.strptime(  # noqa: DTZ007
                    metadata.created_at,
                    "%a, %d %b %Y %H:%M:%S GMT",
                ),
                "number_of_uses": metadata.number_of_uses,
            },
        )

    @property
    @override
    def is_binary(self) -> bool:
        return True
