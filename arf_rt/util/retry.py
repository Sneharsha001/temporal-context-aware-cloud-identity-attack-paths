"""
arf_rt/util/retry.py - Retry decorator with exponential back-off.

Usage::

    from arf_rt.util.retry import retry

    @retry(max_attempts=3, base_delay=0.5, exceptions=(IOError,))
    def flaky_operation():
        ...

    # Or call directly:
    result = retry(max_attempts=5)(my_function)(arg1, arg2)
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, Sequence, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
ExcTypes = Sequence[Type[BaseException]]


class RetryError(RuntimeError):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exc: BaseException):
        self.attempts = attempts
        self.last_exc = last_exc
        super().__init__(
            f"All {attempts} attempt(s) failed. "
            f"Last error: {type(last_exc).__name__}: {last_exc}"
        )


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: ExcTypes = (Exception,),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> Callable:
    """Return a decorator that retries the wrapped function on failure.

    Args:
        max_attempts: Maximum number of times to try the function (including
            the first attempt). Must be >= 1.
        base_delay: Delay in seconds before the first retry.
        backoff: Multiplicative factor applied to the delay after each failure.
        max_delay: Cap for the computed delay (seconds).
        exceptions: Tuple of exception types that should trigger a retry.
            Exceptions not listed here are re-raised immediately.
        on_retry: Optional callback invoked before each retry with
            ``(attempt_number, exception, next_delay)``.

    Returns:
        A decorator that wraps a callable with retry logic.

    Raises:
        RetryError: When all attempts are exhausted.
        Any un-matched exception: Re-raised immediately without retrying.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    exc_tuple = tuple(exceptions)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exc_tuple as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break

                    next_delay = min(delay, max_delay)
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %.2fs",
                        attempt,
                        max_attempts,
                        fn.__qualname__,
                        exc,
                        next_delay,
                    )
                    if on_retry is not None:
                        on_retry(attempt, exc, next_delay)
                    time.sleep(next_delay)
                    delay *= backoff

            assert last_exc is not None  # mypy narrowing
            raise RetryError(attempts=max_attempts, last_exc=last_exc) from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
