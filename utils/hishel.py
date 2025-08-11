from datetime import datetime
from typing import Any, override

import hishel
import httpcore
import msgspec
from hishel._serializers import (
    HEADERS_ENCODING,
    KNOWN_REQUEST_EXTENSIONS,
    KNOWN_RESPONSE_EXTENSIONS,
    Metadata,
)
from hishel._utils import normalized_url


class HishelCachedRequest(msgspec.Struct):
    method: str
    url: str
    headers: list[tuple[str, str]]
    extensions: dict[str, Any]


class HishelCachedResponse(msgspec.Struct):
    status: int
    headers: list[tuple[str, str]]
    content: bytes
    extensions: dict[str, str]


class HishelCacheMetadata(msgspec.Struct):
    cache_key: str
    number_of_uses: int
    created_at: str


class HishelCacheEntry(msgspec.Struct):
    response: HishelCachedResponse
    request: HishelCachedRequest
    metadata: HishelCacheMetadata


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
                    headers=[
                        (k.decode(HEADERS_ENCODING), v.decode(HEADERS_ENCODING))
                        for k, v in response.headers
                    ],
                    content=response.content,
                    extensions={
                        k: v.decode("ascii")
                        for k, v in response.extensions.items()
                        if k in KNOWN_RESPONSE_EXTENSIONS
                    },
                ),
                request=HishelCachedRequest(
                    method=request.method.decode("ascii"),
                    url=normalized_url(request.url),
                    headers=[
                        (k.decode(HEADERS_ENCODING), v.decode(HEADERS_ENCODING))
                        for k, v in request.headers
                    ],
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
            status=full.response.status,
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in full.response.headers
            ],
            content=response_data.content,
            extensions={
                key: value.encode("ascii")
                for key, value in response_data.extensions.items()
                if key in KNOWN_RESPONSE_EXTENSIONS
            },
        )

        request = httpcore.Request(
            method=request_data.method,
            url=request_data.url,
            headers=[
                (key.encode(HEADERS_ENCODING), value.encode(HEADERS_ENCODING))
                for key, value in request_data.headers
            ],
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
