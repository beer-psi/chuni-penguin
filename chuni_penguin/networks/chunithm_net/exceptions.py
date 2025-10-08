from chuni_penguin.networks.errors import NetworkError


class ChuniNetError(NetworkError):
    GENERIC_ERROR = 100001
    LOGIN_FAILURE = 100101
    OLD_GAME_PROFILE = 100106
    INVALID_ACCESS = 120202

    CONNECTION_EXPIRED = 200002
    INVALID_SESSION = 200004
    # 200008

    def __init__(self, code: int, description: str) -> None:
        super().__init__(f"Error code {code}: {description}")
        self.code = code
        self.description = description
