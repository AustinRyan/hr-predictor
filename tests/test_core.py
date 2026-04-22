import json
import logging

import pytest
from sqlalchemy import text
from src.core.db import get_session
from src.core.logging_config import JsonFormatter, configure_logging


def test_get_session_commits_on_success(db_engine) -> None:  # noqa: ARG001
    with get_session() as session:
        result = session.execute(text("SELECT 7 AS seven")).scalar_one()
    assert result == 7


def test_get_session_rolls_back_on_error(db_engine) -> None:  # noqa: ARG001
    class _BoomError(RuntimeError):
        pass

    with pytest.raises(_BoomError):
        with get_session() as session:
            session.execute(text("SELECT 1"))
            raise _BoomError("forced rollback")


def test_json_formatter_emits_valid_json() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="hrp.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.custom_field = "extra"
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "hrp.test"
    assert payload["message"] == "hello world"
    assert payload["custom_field"] == "extra"


def test_json_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("oops")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="hrp.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=None,
            exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert "ValueError: oops" in payload["exc_info"]


def test_configure_logging_idempotent() -> None:
    configure_logging(level="DEBUG")
    root = logging.getLogger()
    handler_count = len(root.handlers)
    configure_logging(level="WARNING")
    assert len(root.handlers) == handler_count
