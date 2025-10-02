from collections.abc import Generator
from http.client import SERVICE_UNAVAILABLE

import httpx
from bs4 import BeautifulSoup

from ._bs4 import BS4_FEATURE
from .exceptions import ChuniNetError, InvalidTokenException, MaintenanceException

_AUTHENTICATION_URL = httpx.URL(
    "https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=chuniex&redirect_url=https://chunithm-net-eng.com/mobile/&back_url=https://chunithm.sega.com/"
)


class ChunithmNetAuth(httpx.Auth):
    """
    Custom authentication for CHUNITHM-NET. Requires following redirects.
    """

    requires_request_body = True
    requires_response_body = True

    def __init__(self, client: httpx.Client | httpx.AsyncClient):
        self.client = client

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        response = yield request

        if response.status_code == SERVICE_UNAVAILABLE:
            raise MaintenanceException

        if response.url.path == "/mobile/error/":
            dom = BeautifulSoup(response.content, BS4_FEATURE)
            error_blocks = dom.select(".block.text_l .font_small")
            code = int(error_blocks[0].text.split(": ", 1)[1])
            description = error_blocks[1].text if len(error_blocks) > 1 else ""

            if code not in {
                ChuniNetError.CONNECTION_EXPIRED,
                ChuniNetError.INVALID_SESSION,
            }:
                raise ChuniNetError(code, description)
        elif response.url.path != "/mobile/":
            return

        auth_response = yield self.client.build_request("GET", _AUTHENTICATION_URL)

        if auth_response.url.host == _AUTHENTICATION_URL.host:
            raise InvalidTokenException

        if str(auth_response.url) == str(request.url):
            return

        # Build a new request so that cookies are refreshed
        yield self.client.build_request(
            request.method,
            request.url,
            content=request.content,
            headers=request.headers,
            extensions=request.extensions,
        )
