"""Consistent error response body + logging."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)


class APIError(HTTPException):
    """Convenience wrapper for internal raises."""


def _error_body(error: str, detail: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": error}
    if detail:
        body["detail"] = detail
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_handler(request: Request, exc: HTTPException):
        if exc.status_code >= 500:
            _log.error(
                "5xx response",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status": exc.status_code,
                    "detail": exc.detail,
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                error=str(exc.detail) if exc.detail else "error",
                detail=None,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # Compact body; FastAPI's default is verbose.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", "invalid request")
        return JSONResponse(
            status_code=422,
            content=_error_body(error="validation_error", detail=f"{field}: {msg}"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        _log.exception(
            "unhandled exception",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=500,
            content=_error_body(error="internal_error"),
        )
