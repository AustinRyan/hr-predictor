import json
import logging
import sys
from datetime import UTC, datetime

from src.core.config import get_settings

_CONFIGURED: bool = False


class JsonFormatter(logging.Formatter):
    """Minimal JSON-line formatter suitable for `jq` / log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in {
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
                "message",
                "module",
                "msecs",
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
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Configure root logger once with a JSON-line stdout handler."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    resolved_level = (level or settings.log_level).upper()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    _CONFIGURED = True
