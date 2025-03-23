import logging
from logging import LogRecord
from typing import override

import structlog
from structlog.stdlib import BoundLogger

from utils.config import config

__all__ = ("logger",)


class StructlogHandler(logging.Handler):
    def __init__(self, level: int = 0) -> None:
        super().__init__(level)
        self._logger: BoundLogger = structlog.get_logger()

    @override
    def emit(self, record: LogRecord) -> None:
        self._logger.log(record.levelno, record.getMessage(), logger=record.name)


log_level = logging.DEBUG if config.dangerous.dev else logging.INFO

discord_logger = logging.getLogger("discord")
discord_logger.setLevel(log_level)
discord_logger.addHandler(StructlogHandler(log_level))

chunithm_net_logger = logging.getLogger("chunithm_net")
chunithm_net_logger.setLevel(log_level)
chunithm_net_logger.addHandler(StructlogHandler(log_level))

processors = structlog.get_config()["processors"][:-1]

if config.dangerous.dev:
    processors.append(structlog.dev.ConsoleRenderer())
else:
    processors.append(structlog.processors.dict_tracebacks)
    processors.append(structlog.processors.JSONRenderer())

structlog.configure(processors=processors)
logger: BoundLogger = structlog.get_logger()
