"""Tests for retry module."""

from __future__ import annotations

import asyncio
import time

import pytest

from arf_rt.util.retry import (
    retry,
    retry_async,
    RetryError,
    RetryContext,
    retry_context,
)


class TestRetryDecorator:
    """Tests for retry decorator."""

    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        call_count = 0

        @retry(max_attempts=3)
        def success():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_failure(self):
        """Test function retries on failure then succeeds."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = flaky()
        assert result == "success"
        assert call_count == 2

    def test_all_attempts_fail(self):
        """Test all attempts fail raises RetryError."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(RetryError) as exc_info:
            always_fail()

        assert exc_info.value.attempts == 3
        assert call_count == 3

    def test_custom_exceptions(self):
        """Test retry only on specified exceptions."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, exceptions=(ValueError,))
        def fail_with_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            fail_with_type_error()

        assert call_count == 1  # No retry for TypeError

    def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        attempts = []

        def callback(attempt, exc, delay):
            attempts.append((attempt, str(exc), delay))

        @retry(max_attempts=3, base_delay=0.01, on_retry=callback)
        def flaky():
            raise ValueError("fail")

        with pytest.raises(RetryError):
            flaky()

        assert len(attempts) == 2  # Called for attempts 1 and 2
        assert attempts[0][0] == 1
        assert attempts[1][0] == 2


class TestRetryAsync:
    """Tests for retry_async decorator."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test async function succeeds on first attempt."""
        call_count = 0

        @retry_async(max_attempts=3)
        async def success():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await success()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test async function retries on failure then succeeds."""
        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        result = await flaky()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self):
        """Test all attempts fail raises RetryError."""
        call_count = 0

        @retry_async(max_attempts=3, base_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(RetryError) as exc_info:
            await always_fail()

        assert exc_info.value.attempts == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_on_retry_callback(self):
        """Test async on_retry callback is called."""
        attempts = []

        async def async_callback(attempt, exc, delay):
            attempts.append((attempt, str(exc), delay))

        @retry_async(max_attempts=3, base_delay=0.01, on_retry=async_callback)
        async def flaky():
            raise ValueError("fail")

        with pytest.raises(RetryError):
            await flaky()

        assert len(attempts) == 2


class TestRetryContext:
    """Tests for RetryContext class."""

    def test_run_success(self):
        """Test successful run."""
        ctx = RetryContext(max_attempts=3)
        result = ctx.run(lambda: "success")
        assert result == "success"
        assert ctx.attempt == 1

    def test_run_retry_then_success(self):
        """Test run with retry then success."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        ctx = RetryContext(max_attempts=3, base_delay=0.01)
        result = ctx.run(flaky)
        assert result == "success"
        assert ctx.attempt == 2

    def test_run_all_fail(self):
        """Test all attempts fail."""
        ctx = RetryContext(max_attempts=3, base_delay=0.01)

        with pytest.raises(RetryError):
            ctx.run(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert ctx.attempt == 3

    def test_run_with_callback(self):
        """Test run with on_retry callback."""
        attempts = []

        def callback(attempt, exc, delay):
            attempts.append((attempt, str(exc), delay))

        ctx = RetryContext(max_attempts=3, base_delay=0.01, on_retry=callback)

        with pytest.raises(RetryError):
            ctx.run(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert len(attempts) == 2

    def test_context_manager(self):
        """Test context manager usage."""
        with RetryContext(max_attempts=3) as ctx:
            result = ctx.run(lambda: "success")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_run_async_success(self):
        """Test async run success."""
        ctx = RetryContext(max_attempts=3)
        result = await ctx.run_async(lambda: "success")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_run_async_retry(self):
        """Test async run with retry."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        ctx = RetryContext(max_attempts=3, base_delay=0.01)
        result = await ctx.run_async(flaky)
        assert result == "success"
        assert ctx.attempt == 2


class TestRetryContextManager:
    """Tests for retry_context function."""

    def test_context_manager(self):
        """Test retry_context creates context."""
        with retry_context(max_attempts=3) as ctx:
            assert isinstance(ctx, RetryContext)
            result = ctx.run(lambda: "success")
        assert result == "success"

    def test_custom_parameters(self):
        """Test custom parameters passed through."""
        with retry_context(max_attempts=5, base_delay=0.5, backoff=3.0) as ctx:
            assert ctx.max_attempts == 5
            assert ctx.base_delay == 0.5
            assert ctx.backoff == 3.0

    def test_exceptions_parameter(self):
        """Test custom exceptions parameter."""
        with retry_context(max_attempts=3, exceptions=(ValueError,)) as ctx:
            assert ctx.exceptions == (ValueError,)


class TestExponentialBackoff:
    """Tests for exponential backoff behavior."""

    def test_backoff_timing(self):
        """Test exponential backoff timing."""
        start = time.time()

        @retry(max_attempts=3, base_delay=0.1, backoff=2.0, max_delay=1.0)
        def flaky():
            raise ValueError("fail")

        with pytest.raises(RetryError):
            flaky()

        elapsed = time.time() - start
        # Should sleep ~0.1 + 0.2 = 0.3 seconds (approximately)
        assert elapsed >= 0.25
        assert elapsed < 1.0

    def test_max_delay_cap(self):
        """Test max_delay caps the backoff."""
        start = time.time()

        @retry(max_attempts=3, base_delay=1.0, backoff=10.0, max_delay=0.1)
        def flaky():
            raise ValueError("fail")

        with pytest.raises(RetryError):
            flaky()

        elapsed = time.time() - start
        # Should sleep ~0.1 + 0.1 = 0.2 seconds (capped at max_delay)
        assert elapsed >= 0.15
        assert elapsed < 0.5