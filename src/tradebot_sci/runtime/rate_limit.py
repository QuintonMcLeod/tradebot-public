from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Iterable, TypeVar

import httpx

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_attempts: int = 4,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.5,
    retry_on_statuses: Iterable[int] = (429, 500, 502, 503, 504),
) -> Callable[[F], F]:
    """Politely nags the API until it answers or rage-quits."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            attempt = 0
            last_exc: Exception | None = None
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # pragma: no cover - defensive
                    last_exc = exc
                    attempt += 1
                    if not _is_retryable(exc, retry_on_statuses):
                        logger.warning("Non-retryable error, giving up: %s", exc)
                        raise
                    sleep_for = _calc_sleep(delay, max_delay, jitter, exc)
                    logger.info(
                        "Retrying after %.2fs (attempt %s/%s)", sleep_for, attempt, max_attempts
                    )
                    time.sleep(sleep_for)
                    delay = min(delay * 2, max_delay)
            if last_exc:
                raise last_exc

        return wrapper  # type: ignore

    return decorator


def _is_retryable(exc: Exception, retry_statuses: Iterable[int]) -> bool:
    """Checks if the exception deserves another love letter."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in retry_statuses
    if isinstance(exc, httpx.RequestError):
        return True
    return False


def _calc_sleep(delay: float, max_delay: float, jitter: float, exc: Exception) -> float:
    """Adds jitter so the API doesn't think we're a bot... even though we are."""
    base = min(delay, max_delay)
    wiggle = random.uniform(-jitter, jitter)
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return max(0.1, base + wiggle)
