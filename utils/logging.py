import atexit
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from queue import Queue
from typing import Any, ClassVar, Optional

from utils.config import config


def is_docker() -> bool:
    path = Path("/proc/self/cgroup")

    with path.open() as f:
        return Path("/.dockerenv").exists() or (
            path.is_file() and any("docker" in line for line in f)
        )


def stream_supports_colour(stream: Any) -> bool:
    is_a_tty = hasattr(stream, "isatty") and stream.isatty()

    # Pycharm and Vscode support colour in their inbuilt editors
    if "PYCHARM_HOSTED" in os.environ or os.environ.get("TERM_PROGRAM") == "vscode":
        return is_a_tty

    if sys.platform != "win32":
        # Docker does not consistently have a tty attached to it
        return is_a_tty or is_docker()

    # ANSICON checks for things like ConEmu
    # WT_SESSION checks if this is Windows Terminal
    return is_a_tty and ("ANSICON" in os.environ or "WT_SESSION" in os.environ)


class ColorFormatter(logging.Formatter):
    # ANSI codes are a bit weird to decipher if you're unfamiliar with them, so here's a refresher
    # It starts off with a format like \x1b[XXXm where XXX is a semicolon separated list of commands
    # The important ones here relate to colour.
    # 30-37 are black, red, green, yellow, blue, magenta, cyan and white in that order
    # 40-47 are the same except for the background
    # 90-97 are the same but "bright" foreground
    # 100-107 are the same as the bright ones but for the background.
    # 1 means bold, 2 means dim, 0 means reset, and 4 means underline.

    LEVEL_COLOURS: ClassVar[list[tuple[int, str]]] = [
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[41m"),
    ]

    FORMATS: ClassVar[dict[int, logging.Formatter]] = {
        level: logging.Formatter(
            f"\x1b[30;1m%(asctime)s\x1b[0m {colour}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        for level, colour in LEVEL_COLOURS
    }

    def format(self, record):
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]

        # Override the traceback to always print in red
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"

        output = formatter.format(record)

        # Remove the cache layer
        record.exc_text = None
        return output


class QueueListenerHandler(logging.handlers.QueueHandler):
    def __init__(self, *handlers: logging.Handler) -> None:
        super().__init__(Queue(-1))
        self._listener = logging.handlers.QueueListener(
            self.queue,
            *handlers,
        )

        self._listener.start()
        atexit.register(self._listener.stop)

    def emit(self, record):
        try:
            self.enqueue(record)
        except Exception:  # noqa: BLE001
            self.handleError(record)


def setup_handler(
    handler: logging.Handler,
    formatter: Optional[logging.Formatter] = None,
) -> logging.Handler:
    if formatter is None:
        if isinstance(handler, logging.StreamHandler) and stream_supports_colour(
            handler.stream
        ):
            formatter = ColorFormatter()
        else:
            formatter = logging.Formatter(
                "[{asctime}] [{levelname:<8}] {name}: {message}",
                datefmt="%Y-%m-%d %H:%M:%S",
                style="{",
            )

    handler.setFormatter(formatter)
    return handler


def setup_logging(
    name: str,
    *,
    handler: Optional[logging.Handler] = None,
    formatter: Optional[logging.Formatter] = None,
    level: int = logging.INFO,
):
    if handler is None:
        handler = logging.StreamHandler()

    if formatter is None:
        if isinstance(handler, logging.StreamHandler) and stream_supports_colour(
            handler.stream
        ):
            formatter = ColorFormatter()
        else:
            formatter = logging.Formatter(
                "[{asctime}] [{levelname:<8}] {name}: {message}",
                datefmt="%Y-%m-%d %H:%M:%S",
                style="{",
            )

    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


console_handler = setup_handler(logging.StreamHandler())
queue_handler = QueueListenerHandler(
    console_handler,
    setup_handler(
        logging.handlers.RotatingFileHandler(
            filename="data/chuni_penguin.log",
            encoding="utf-8",
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=5,  # Rotate through 5 files
        ),
    ),
)

setup_logging(
    "chunithm_net",
    handler=queue_handler,
    level=logging.DEBUG if config.dangerous.dev else logging.INFO,
)

logger = setup_logging(
    "chuni_penguin",
    handler=queue_handler,
    level=logging.DEBUG if config.dangerous.dev else logging.INFO,
)
