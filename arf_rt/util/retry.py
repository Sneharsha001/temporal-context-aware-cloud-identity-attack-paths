"""
arf_rt/util/retry.py - Retry decorator with exponential back-off.

Usage::

    from arf_rt.util.retry import retry, retry_async, RetryContext

    @retry(max_attempts=3, base_delay=0.5, exceptions=(IOError,))
    def flaky_operation():
        ...

    @retry_async(max_attempts=3, base_delay=0.5)
    async def async_flaky_operation():
        ...

    # Context manager usage:
    with RetryContext(max_attempts=3) as ctx:
        ctx.run(flaky_operation)

    # Or call directly:
    result = retry(max_attempts=5)(my_function)(arg1, arg2)
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator, Sequence, Type, TypeVar

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


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: ExcTypes = (Exception,),
    on_retry: Callable[[int, BaseException, float], Any] | None = None,
) -> Callable:
    """Return a decorator that retries an async function on failure.

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
        A decorator that wraps an async callable with retry logic.

    Raises:
        RetryError: When all attempts are exhausted.
        Any un-matched exception: Re-raised immediately without retrying.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    exc_tuple = tuple(exceptions)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
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
                        if asyncio.iscoroutinefunction(on_retry):
                            await on_retry(attempt, exc, next_delay)
                        else:
                            on_retry(attempt, exc, next_delay)
                    await asyncio.sleep(next_delay)
                    delay *= backoff

            assert last_exc is not None
            raise RetryError(attempts=max_attempts, last_exc=last_exc) from last_exc

        return wrapper  # type: ignore[return-value]

    return decorator


class RetryContext:
    """Context manager for retrying operations.

    Usage::

        with RetryContext(max_attempts=3) as ctx:
            result = ctx.run(my_function, arg1, arg2)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        backoff: float = 2.0,
        max_delay: float = 60.0,
        exceptions: ExcTypes = (Exception,),
        on_retry: Callable[[int, BaseException, float], None] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.backoff = backoff
        self.max_delay = max_delay
        self.exceptions = tuple(exceptions)
        self.on_retry = on_retry
        self.attempt = 0
        self.last_exc: BaseException | None = None

    def __enter__(self) -> "RetryContext":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False  # Don't suppress exceptions

    def run(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Run a function with retry logic."""
        self.attempt = 0
        self.last_exc = None
        delay = self.base_delay

        for attempt in range(1, self.max_attempts + 1):
            self.attempt = attempt
            try:
                return fn(*args, **kwargs)
            except self.exceptions as exc:
                self.last_exc = exc
                if attempt == self.max_attempts:
                    break

                next_delay = min(delay, self.max_delay)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %.2fs",
                    attempt,
                    self.max_attempts,
                    exc,
                    next_delay,
                )
                if self.on_retry is not None:
                    self.on_retry(attempt, exc, next_delay)
                time.sleep(next_delay)
                delay *= self.backoff

        assert self.last_exc is not None
        raise RetryError(attempts=self.max_attempts, last_exc=self.last_exc) from self.last_exc

    async def run_async(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Run an async function with retry logic."""
        self.attempt = 0
        self.last_exc = None
        delay = self.base_delay

        for attempt in range(1, self.max_attempts + 1):
            self.attempt = attempt
            try:
                return await fn(*args, **kwargs)
            except self.exceptions as exc:
                self.last_exc = exc
                if attempt == self.max_attempts:
                    break

                next_delay = min(delay, self.max_delay)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %.2fs",
                    attempt,
                    self.max_attempts,
                    exc,
                    next_delay,
                )
                if self.on_retry is not None:
                    if asyncio.iscoroutinefunction(self.on_retry):
                        await self.on_retry(attempt, exc, next_delay)
                    else:
                        self.on_retry(attempt, exc, next_delay)
                await asyncio.sleep(next_delay)
                delay *= self.backoff

        assert self.last_exc is not None
        raise RetryError(attempts=self.max_attempts, last_exc=self.last_exc) from self.last_exc


@contextmanager
def retry_context(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: ExcTypes = (Exception,),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> Generator[RetryContext, None, None]:
    """Create a retry context manager.

    Usage::

        with retry_context(max_attempts=3) as ctx:
            result = ctx.run(my_function)
    """
    ctx = RetryContext(
        max_attempts=max_attempts,
        base_delay=base_delay,
        backoff=backoff,
        max_delay=max_delay,
        exceptions=exceptions,
        on_retry=on_retry,
    )
    try:
        yield ctx
    finally:
        pass
