class ChuniBotError(Exception):
    """Base class for all bot exceptions."""


class MissingDetailedParams(ChuniBotError):
    """Raised when a record is missing params for accessing details."""

    def __init__(self) -> None:
        super().__init__("Cannot fetch song details if song.detailed is None.")


class MissingConfiguration(ChuniBotError):
    """Raised when a configuration key is missing."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Configuration file is missing key {key!r}.")
