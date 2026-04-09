from http.client import SERVICE_UNAVAILABLE, responses

import httpx

from .errors import HTTPError, MaintenanceError


async def raise_on_server_errors(response: httpx.Response):
    if response.status_code == SERVICE_UNAVAILABLE:
        raise MaintenanceError

    if response.status_code >= 500:
        raise HTTPError(response.status_code, responses.get(response.status_code))
