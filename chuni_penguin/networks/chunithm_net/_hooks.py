import contextlib
from collections.abc import Generator
from http.client import SERVICE_UNAVAILABLE

import httpx
from bs4 import BeautifulSoup

from chuni_penguin.networks.errors import AuthenticationError, MaintenanceError

from ._bs4 import BS4_FEATURE
from .exceptions import ChuniNetError

_AUTHENTICATION_URL = httpx.URL(
    "https://lng-tgk-aime-gw.am-all.net/common_auth/login"
    "?site_id=chuniex"
    "&redirect_url=https://chunithm-net-eng.com/mobile/"
    "&back_url=https://chunithm.sega.com/"
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

        error: ChuniNetError | None = response.extensions.get("chunithm_net_error")

        if response.url.path != "/mobile/" and error is None:
            return

        auth_response = yield self.client.build_request("GET", _AUTHENTICATION_URL)

        if auth_response.url.host == _AUTHENTICATION_URL.host:
            raise AuthenticationError

        if str(auth_response.url) == str(request.url):
            return

        # refresh cookies on the request
        with contextlib.suppress(KeyError):
            del request.headers["cookie"]
            del request.headers["cookie2"]  # pragma: no cover

        request.extensions["chunithm_net_reauth"] = True

        self.client.cookies.set_cookie_header(request)

        yield request


async def raise_on_chunithm_net_error(response: httpx.Response):
    if response.url.path != "/mobile/error/":
        return

    dom = BeautifulSoup(await response.aread(), BS4_FEATURE)
    error_blocks = dom.select(".block.text_l .font_small")
    code = int(error_blocks[0].text.split(": ", 1)[1])
    description = error_blocks[1].text if len(error_blocks) > 1 else ""

    error = response.extensions["chunithm_net_error"] = ChuniNetError(code, description)

    if (
        code not in {ChuniNetError.CONNECTION_EXPIRED, ChuniNetError.INVALID_SESSION}
        or "chunithm_net_reauth" in response.request.extensions
    ):
        raise error


async def raise_on_maintenance(response: httpx.Response):
    if response.status_code == SERVICE_UNAVAILABLE:
        raise MaintenanceError
