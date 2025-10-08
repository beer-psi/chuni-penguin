class NetworkError(Exception):
    """Base class for network errors."""


class AuthenticationError(NetworkError):
    """Authenticating with the network failed."""


class SongNotFound(NetworkError):
    """The song requested does not exist on the network."""


class ChartNotFound(NetworkError):
    """The chart requested does not exist on the network."""


class MaintenanceError(NetworkError):
    """The network is under maintenance."""


class AlreadyFriends(NetworkError):
    """The user tried to add someone they're already friends with."""


class InvalidFriendCode(NetworkError):
    """The friend code is invalid."""
