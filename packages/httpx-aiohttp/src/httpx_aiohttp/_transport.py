import asyncio
import contextlib
import itertools
from typing import TYPE_CHECKING

import aiohttp
import httpx
from httpx._config import DEFAULT_LIMITS

if TYPE_CHECKING:
    import ssl
    from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator

    import aiohappyeyeballs
    from httpx._transports.default import SOCKET_OPTION

AIOHTTP_EXC_MAP: dict[type[aiohttp.ClientError], type[Exception]] = {
    # client exceptions
    aiohttp.ClientPayloadError: httpx.ReadError,
    aiohttp.InvalidUrlRedirectClientError: httpx.UnsupportedProtocol,
    aiohttp.NonHttpUrlRedirectClientError: httpx.UnsupportedProtocol,
    # connection errors
    aiohttp.ClientConnectionError: httpx.NetworkError,
    aiohttp.ClientConnectorError: httpx.ConnectError,
    aiohttp.ServerTimeoutError: httpx.TimeoutException,
    aiohttp.ConnectionTimeoutError: httpx.ConnectTimeout,
    aiohttp.SocketTimeoutError: httpx.ReadTimeout,
    aiohttp.ClientProxyConnectionError: httpx.ProxyError,
}


@contextlib.contextmanager
def map_aiohttp_exceptions() -> "Iterator[None]":
    global AIOHTTP_EXC_MAP

    try:
        yield
    except Exception as exc:
        mapped_exc = None

        for from_exc, to_exc in AIOHTTP_EXC_MAP.items():
            if not isinstance(exc, from_exc):
                continue
            # We want to map to the most specific exception we can find.
            # Eg if `exc` is an `httpcore.ReadTimeout`, we want to map to
            # `httpx.ReadTimeout`, not just `httpx.TimeoutException`.
            if mapped_exc is None or issubclass(to_exc, mapped_exc):
                mapped_exc = to_exc

        if mapped_exc is None:  # pragma: no cover
            raise

        message = str(exc)
        raise mapped_exc(message) from exc


def exponential_backoff(factor: float) -> "Iterator[float]":
    """
    Generate a geometric sequence that has a ratio of 2 and starts with 0.

    For example:
    - `factor = 2`: `0, 2, 4, 8, 16, 32, 64, ...`
    - `factor = 3`: `0, 3, 6, 12, 24, 48, 96, ...`
    """
    yield 0

    for n in itertools.count():
        yield factor * 2**n


class RetryMiddleware:
    def __init__(self, retries: int, factor: float = 0.5):
        self.retries = retries
        self.factor = factor

    async def __call__(
        self, req: aiohttp.ClientRequest, handler: aiohttp.ClientHandlerType
    ):
        retries_left = self.retries
        delays = exponential_backoff(self.factor)

        while True:
            try:
                resp = await handler(req)
            except (aiohttp.ClientConnectorError, aiohttp.ConnectionTimeoutError):
                if retries_left <= 0:
                    raise

                retries_left -= 1
                delay = next(delays)

                await asyncio.sleep(delay)
            else:
                return resp


class AIOHTTPResponseStream(httpx.AsyncByteStream):
    def __init__(self, response: aiohttp.ClientResponse) -> None:
        self._response = response

    async def __aiter__(self) -> "AsyncIterator[bytes]":
        with map_aiohttp_exceptions():
            async for part, _end_of_http_chunk in self._response.content.iter_chunks():
                yield part

    async def aclose(self) -> None:
        self._response.release()
        await self._response.wait_for_close()


class AIOHTTPTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        cert: str | tuple[str, str] | tuple[str, str, str] | None = None,
        limits: httpx.Limits = DEFAULT_LIMITS,
        proxy: httpx.URL | str | httpx.Proxy | None = None,
        uds: str | None = None,
        local_address: str | None = None,
        retries: int = 0,
        socket_options: "Iterable[SOCKET_OPTION] | None" = None,
        client: "aiohttp.ClientSession | Callable[[], Awaitable[aiohttp.ClientSession]] | None" = None,
        *,
        verify: "ssl.SSLContext | str | bool" = True,
        trust_env: bool = True,
    ) -> None:
        ssl_context = httpx.create_ssl_context(verify, cert, trust_env)

        if isinstance(proxy, httpx.Proxy):
            self.proxy = proxy
        elif proxy is not None:
            self.proxy = httpx.Proxy(proxy, ssl_context=ssl_context)
        else:
            self.proxy = None

        self.ssl_context = ssl_context
        self.limits = limits
        self.uds = uds
        self.local_address = local_address
        self._retry_middleware = RetryMiddleware(retries)
        self.socket_options = (
            list(socket_options) if socket_options is not None else None
        )
        self.client = client

    def _socket_factory(self, addr_info: "aiohappyeyeballs.AddrInfoType"):
        import socket

        family, type_, proto, _, __ = addr_info

        sock = socket.socket(family=family, type=type_, proto=proto)

        if not self.socket_options:
            return sock

        for option in self.socket_options:
            sock.setsockopt(*option)  # pyright: ignore[reportCallIssue, reportArgumentType]

        return sock

    @property
    def retries(self):
        return self._retry_middleware.retries

    @retries.setter
    def retries(self, value: int):
        self._retry_middleware.retries = value

    async def get_client(self) -> aiohttp.ClientSession:
        if callable(self.client):
            self.client = await self.client()
            return self.client

        if isinstance(self.client, aiohttp.ClientSession):
            return self.client

        limit = (
            self.limits.max_connections
            if self.limits.max_connections is not None
            else 100
        )

        if self.uds is not None:
            connector = aiohttp.UnixConnector(
                self.uds,
                keepalive_timeout=self.limits.keepalive_expiry,
                limit=limit,
            )
        else:
            local_addr = (
                (self.local_address, 0) if self.local_address is not None else None
            )

            connector = aiohttp.TCPConnector(
                ssl=self.ssl_context,
                local_addr=local_addr,
                keepalive_timeout=self.limits.keepalive_expiry,
                limit=limit,
                socket_factory=self._socket_factory,
            )

        self.client = aiohttp.ClientSession(connector=connector)

        return self.client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        client = await self.get_client()

        server_hostname = request.extensions.get("sni_hostname", None)

        timeouts = request.extensions.get("timeout", {})
        timeout = aiohttp.ClientTimeout(
            connect=timeouts.get("pool"),
            sock_read=timeouts.get("read"),
            sock_connect=timeouts.get("connect"),
        )

        proxy = str(self.proxy.url) if self.proxy is not None else None
        proxy_auth = (
            aiohttp.BasicAuth(self.proxy.auth[0], self.proxy.auth[1])
            if self.proxy is not None and self.proxy.auth is not None
            else None
        )
        proxy_headers = self.proxy.headers if self.proxy is not None else None

        with map_aiohttp_exceptions():
            try:
                data = request.content

                if not data:
                    data = None
            except httpx.RequestNotRead:
                data = request.stream

                request.headers.pop("transfer-encoding", None)

            response = await client.request(
                method=request.method,
                url=str(request.url),
                data=data,
                headers=request.headers,
                allow_redirects=False,
                compress=False,
                proxy=proxy,
                proxy_auth=proxy_auth,
                timeout=timeout,
                ssl=self.ssl_context,
                server_hostname=server_hostname,
                proxy_headers=proxy_headers,
                auto_decompress=False,
                middlewares=(self._retry_middleware,),
            )

        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            content=AIOHTTPResponseStream(response),
            request=request,
            extensions={
                "http_version": b"HTTP/1.1",
                "reason_phrase": (
                    response.reason.encode() if response.reason is not None else b""
                ),
            },
        )

    async def aclose(self) -> None:
        client = await self.get_client()
        await client.close()
