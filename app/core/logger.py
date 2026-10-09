import logging
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal

import logfire

from settings import get_config

LogLevel = Literal["info", "error", "debug", "warning", "fatal"]


@cache
def _logfire() -> logfire.Logfire:
    """Configured once per process, on first use, so module-level loggers don't load settings at import time."""
    config = get_config()
    return logfire.configure(
        token=config.LOGFIRE_TOKEN or None,
        send_to_logfire="if-token-present",
        service_name="techlead",
        environment=config.APP_ENV,
    )


def configure_logging(level: int = logging.INFO) -> None:
    """Configure Logfire and route stdlib ``logging`` (``ai/``, CrewAI, uvicorn, httpx) through it."""
    root = logging.getLogger()
    root.handlers[:] = [logfire.LogfireLoggingHandler(logfire_instance=_logfire())]
    root.setLevel(level)


@dataclass
class Logger:

    name: str

    @property
    def config(self) -> logfire.Logfire:
        return _logfire()

    def fire(self, message: str, level: LogLevel | None = 'info', **attributes: Any) -> None:
        """Log ``message`` with structured ``attributes``; pass ``_exc_info=True`` to attach the current exception."""
        with self.config.span(self.name):
            match level:
                case "info":
                    self.config.info(message, **attributes)
                case "error":
                    self.config.error(message, **attributes)
                case "debug":
                    self.config.debug(message, **attributes)
                case "warning":
                    self.config.warning(message, **attributes)
                case "fatal":
                    self.config.fatal(message, **attributes)
                case _:
                    self.config.info(message, **attributes)


if __name__ == "__main__":
    logger = Logger(name="app")
    logger.fire(message="hi")
