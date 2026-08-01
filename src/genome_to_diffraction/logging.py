"""Structured JSON logging without global configuration side effects."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Literal

_STANDARD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render one compact JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a record with stable core fields and serialisable extras."""

        timestamp = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, Any] = {
            "timestamp": timestamp.isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)


class HumanFormatter(logging.Formatter):
    """Render concise progress logs while retaining structured context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a record and append non-standard fields as key-value pairs."""

        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_")
        }
        suffix = " ".join(f"{key}={value}" for key, value in sorted(context.items()))
        message = f"{record.levelname.lower()}: {record.getMessage()}"
        if suffix:
            message = f"{message} [{suffix}]"
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return message


class DynamicStderrHandler(logging.StreamHandler[Any]):
    """Write to the current stderr so redirected/captured streams do not go stale."""

    def emit(self, record: logging.LogRecord) -> None:
        """Refresh the stream immediately before rendering a record."""

        self.stream = sys.stderr
        super().emit(record)


def configure_logging(
    *,
    level: int = logging.INFO,
    logger_name: str = "genome_to_diffraction",
    log_format: Literal["json", "human"] = "json",
) -> logging.Logger:
    """Configure and return an isolated package logger."""

    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    handler = DynamicStderrHandler()
    formatter: logging.Formatter = (
        JsonFormatter() if log_format == "json" else HumanFormatter()
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def parse_log_level(value: str) -> int:
    """Convert a CLI log-level name to a logging level."""

    level = logging.getLevelNamesMapping().get(value.upper())
    if level is None:
        choices = ", ".join(("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
        raise ValueError(f"unknown log level {value!r}; choose one of {choices}")
    return level
