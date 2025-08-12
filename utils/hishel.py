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


class HishelCachedRequest(msgspec.Struct, array_like=True):
    method: bytes
    url: str
    headers: list[tuple[bytes, bytes]]
    extensions: dict[str, Any]


class HishelCachedResponse(msgspec.Struct, array_like=True):
    status: int
    headers: list[tuple[bytes, bytes]]
    content: bytes
    extensions: dict[str, bytes]


class HishelCacheMetadata(msgspec.Struct, array_like=True):
    cache_key: str
    number_of_uses: int
    created_at: datetime


class HishelCacheEntry(msgspec.Struct, array_like=True):
    response: HishelCachedResponse
    request: HishelCachedRequest
    metadata: HishelCacheMetadata


class HishelMsgspecSerializer(hishel.BaseSerializer):
    def __init__(self) -> None:
        super().__init__()
        self._encoder = msgspec.msgpack.Encoder()
        self._decoder = msgspec.msgpack.Decoder(HishelCacheEntry)

    @override
    def dumps(
        self,
        response: httpcore.Response,
        request: httpcore.Request,
        metadata: Metadata,
    ) -> str | bytes:
        return self._encoder.encode(
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
                    created_at=metadata["created_at"],
                ),
            )
        )

    @override
    def loads(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, data: bytes
    ) -> tuple[httpcore.Response, httpcore.Request, hishel._serializers.Metadata]:
        full = self._decoder.decode(data)
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
                "created_at": metadata.created_at,
                "number_of_uses": metadata.number_of_uses,
            },
        )

    @property
    @override
    def is_binary(self) -> bool:
        return True
