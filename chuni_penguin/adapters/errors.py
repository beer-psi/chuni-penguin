from http.client import SERVICE_UNAVAILABLE, responses


class NetworkError(Exception):
    """Base class for network errors."""


class HTTPError(NetworkError):
    """Generic errors for unrecoverable HTTP status codes (usually 5xx)."""

    def __init__(self, code: int, text: str | None):
        if text is not None:
            super().__init__(f"HTTP error {code}: {text}")
        else:
            super().__init__(f"HTTP error {code}")

        self.code: int = code
        self.text: str | None = text


class AuthenticationError(NetworkError):
    """Authenticating with the network failed."""


class NoCardsRegistered(AuthenticationError):
    """The account does not have any Aime cards registered."""


class SongNotFound(NetworkError):
    """The song requested does not exist on the network."""


class ChartNotFound(NetworkError):
    """The chart requested does not exist on the network."""


class MaintenanceError(HTTPError):
    """The network is under maintenance."""

    def __init__(self):
        super().__init__(SERVICE_UNAVAILABLE, responses[SERVICE_UNAVAILABLE])


class AlreadyFriends(NetworkError):
    """The user tried to add someone they're already friends with."""


class InvalidFriendCode(NetworkError):
    """The friend code is invalid."""
