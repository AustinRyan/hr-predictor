"""Redis-cached-decorator for read endpoints. Gracefully degrades to
direct execution if Redis is unreachable."""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from redis.exceptions import RedisError

from src.core.redis_client import get_redis

_log = logging.getLogger(__name__)

_T = TypeVar("_T")

_KEY_SEPARATOR = ":"


def _stable_key(
    prefix: str,
    args: tuple,
    kwargs: dict,
    model_version: str | None,
) -> str:
    """Deterministic cache key from function args + model version.

    Requires all arguments be JSON-serializable or primitive. Non-serializable
    args (like Session) must be excluded by caller via `exclude`.
    """
    payload = {"args": args, "kwargs": kwargs, "model_version": model_version}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]
    return f"{prefix}{_KEY_SEPARATOR}{digest}"


def cached(
    ttl_seconds: int,
    key_prefix: str,
    *,
    exclude: tuple[str, ...] = ("db", "session", "redis", "request"),
    model: type[BaseModel] | None = None,
    model_list: bool = False,
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Decorator: cache the result in Redis for ttl_seconds.

    `exclude` — argument names never included in the cache key (e.g., DB
    sessions). Defaults cover the common FastAPI DI args.

    `model` — Pydantic class; if given, cache stores JSON via
    `.model_dump_json()` and deserializes via `.model_validate_json`. If
    `model_list=True`, value is a list of model instances.

    Graceful degradation: if Redis raises, log a warning and fall through to
    the direct call.
    """

    def decorator(func: Callable[..., _T]) -> Callable[..., _T]:
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            key_args = {k: v for k, v in bound.arguments.items() if k not in exclude}
            # Build key
            model_version = _current_model_version(bound.arguments)
            cache_key = _stable_key(key_prefix, tuple(key_args.items()), {}, model_version)

            try:
                r = get_redis()
                raw = r.get(cache_key)
                if raw is not None:
                    return _deserialize(raw, model, model_list)
            except RedisError as exc:
                _log.warning(
                    "redis get failed, serving direct",
                    extra={"err": str(exc), "key": cache_key},
                )

            result = (
                await func(*args, **kwargs)
                if inspect.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )

            try:
                r = get_redis()
                r.setex(cache_key, ttl_seconds, _serialize(result, model, model_list))
            except RedisError as exc:
                _log.warning(
                    "redis set failed",
                    extra={"err": str(exc), "key": cache_key},
                )
            return result

        return wrapper

    return decorator


def _current_model_version(bound_args: dict) -> str | None:
    """Pull the model version out of a request scope if available — used
    as a cache-invalidation key so redeployments auto-flush."""
    req = bound_args.get("request") or bound_args.get("req")
    if req is None:
        return None
    loaded = getattr(getattr(req, "app", None), "state", None)
    loaded = getattr(loaded, "loaded_model", None)
    return loaded.version if loaded is not None else None


def _serialize(obj: Any, model: type[BaseModel] | None, is_list: bool) -> str:
    if model is None:
        return json.dumps(obj, default=str)
    if is_list:
        return "[" + ",".join(item.model_dump_json() for item in obj) + "]"
    return obj.model_dump_json()


def _deserialize(raw: bytes | str, model: type[BaseModel] | None, is_list: bool) -> Any:
    if model is None:
        return json.loads(raw)
    text = raw.decode() if isinstance(raw, bytes) else raw
    if is_list:
        parsed = json.loads(text)
        return [model.model_validate(item) for item in parsed]
    return model.model_validate_json(text)
