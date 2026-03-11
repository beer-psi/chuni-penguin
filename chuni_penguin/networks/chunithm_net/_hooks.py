import contextlib
import re
from collections.abc import Generator
from http.client import METHOD_NOT_ALLOWED

import httpx
from bs4 import BeautifulSoup
from bs4.filter import SoupStrainer

from chuni_penguin.networks.errors import (
    AuthenticationError,
    MaintenanceError,
    NoCardsRegistered,
)

from ._bs4 import BS4_FEATURE
from .exceptions import ChuniNetError

_AUTHENTICATION_URL = httpx.URL(
    "https://lng-tgk-aime-gw.am-all.net/common_auth/login"
    "?site_id=chuniex"
    "&redirect_url=https://chunithm-net-eng.com/mobile/"
    "&back_url=https://chunithm.sega.com/"
)
_COMMON_AUTH_REDIRECT_URL = httpx.URL(
    "https://lng-tgk-aime-gw.am-all.net/common_auth/redirect"
)
_ADD_ACCESS_CODE_URL = httpx.URL("https://common-access.am-all.net/access/code/add")


class ChunithmNetAuth(httpx.Auth):
    """
    Custom authentication for CHUNITHM-NET. Requires following redirects.
    """

    __slots__ = ("client", "password", "username")

    requires_request_body = True
    requires_response_body = True

    def __init__(
        self,
        client: httpx.Client | httpx.AsyncClient,
        *,
        username: str | None = None,
        password: str | None = None,
    ):
        self.client = client
        self.username = username
        self.password = password

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        response = yield request

        error: ChuniNetError | None = response.extensions.get("chunithm_net_error")

        if response.url.path != "/mobile/" and error is None:
            return

        auth_response = yield self.client.build_request("GET", _AUTHENTICATION_URL)

        if (
            auth_response.url.host == _AUTHENTICATION_URL.host
            and auth_response.url.path == _AUTHENTICATION_URL.path
        ):
            if self.username is None or self.password is None:
                msg = "The provided access token is invalid."
                raise AuthenticationError(msg)

            auth_response = yield self.client.build_request(
                "POST",
                "https://lng-tgk-aime-gw.am-all.net/common_auth/login/sid/",
                data={
                    "retention": "1",
                    "sid": self.username,
                    "password": self.password,
                },
            )

            if (
                auth_response.url.host == _AUTHENTICATION_URL.host
                and auth_response.url.path == _AUTHENTICATION_URL.path
            ):
                msg = "The provided username or password is invalid, or the account has TOTP enabled."
                raise AuthenticationError(msg)

        if (
            auth_response.url.host == _COMMON_AUTH_REDIRECT_URL.host
            and auth_response.url.path == _COMMON_AUTH_REDIRECT_URL.path
        ):
            soup = BeautifulSoup(
                auth_response.content, BS4_FEATURE, parse_only=SoupStrainer("form")
            )
            form = soup.find("form")

            if (
                form is not None
                and form["action"] == "https://common-access.am-all.net/access/code/add"
            ):
                msg = (
                    "The account does not have any access codes registered. "
                    "Please register an access code on https://my-aime.net before logging in."
                )
                raise NoCardsRegistered(msg)

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
    # When trying to access the leaderboard during maintenance period
    if (
        response.request.url.path.startswith("/mobile/ranking/")
        and response.status_code == METHOD_NOT_ALLOWED
    ):
        raise MaintenanceError

    if response.url.path != "/mobile/error/":
        return

    dom = BeautifulSoup(
        await response.aread(),
        BS4_FEATURE,
        parse_only=SoupStrainer(class_=re.compile("(?:block text_l|text_l block)")),
    )
    error_blocks = dom.select(".block.text_l .font_small")
    code = int(error_blocks[0].text.split(": ", 1)[1])
    description = error_blocks[1].text if len(error_blocks) > 1 else ""

    error = response.extensions["chunithm_net_error"] = ChuniNetError(code, description)

    if (
        code not in {ChuniNetError.CONNECTION_EXPIRED, ChuniNetError.INVALID_SESSION}
        or "chunithm_net_reauth" in response.request.extensions
    ):
        raise error
