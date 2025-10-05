class ChuniNetException(Exception):
    pass


class InvalidTokenException(ChuniNetException):
    pass


class MaintenanceException(ChuniNetException):
    pass


class ChuniNetError(ChuniNetException):
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


class InvalidFriendCode(ChuniNetException):
    pass


class AlreadyAddedAsFriend(ChuniNetException):
    pass
