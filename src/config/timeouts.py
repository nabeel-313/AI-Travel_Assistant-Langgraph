"""
Centralized timeout configuration for production-grade network operations.

This module provides:
- Standard timeout values for all network operations
- A reusable `with_timeout` helper for wrapping async coroutines
- A `timeout_context` for fine-grained timeout control
- Environment-variable overrides for ops flexibility

Production Best Practices Applied:
1. **Bounded waits**: Every network call has a hard upper bound
2. **Graceful degradation**: Timeouts return safe defaults, never crash
3. **Observability**: All timeouts are logged with context
4. **Configurability**: Values can be tuned via env vars without code changes
5. **Layered timeouts**: Different timeouts for different operation types
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from src.loggers import Logger

logger = Logger(__name__).get_logger()

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Timeout constants (seconds) - production defaults
# ---------------------------------------------------------------------------
# All values can be overridden via environment variables for ops flexibility.

def _env_float(name: str, default: float) -> float:
    """Read a float from env, falling back to default."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# LLM (model provider) timeouts
DEFAULT_LLM_TIMEOUT = _env_float("LLM_TIMEOUT", 30.0)        # Standard LLM calls
LONG_LLM_TIMEOUT = _env_float("LONG_LLM_TIMEOUT", 60.0)      # Itinerary generation, complex prompts
SHORT_LLM_TIMEOUT = _env_float("SHORT_LLM_TIMEOUT", 15.0)    # Quick extractions (city, query)

# External HTTP API timeouts (SerpAPI, OpenWeatherMap, etc.)
DEFAULT_HTTP_TIMEOUT = _env_float("HTTP_TIMEOUT", 30.0)
WEATHER_HTTP_TIMEOUT = _env_float("WEATHER_HTTP_TIMEOUT", 20.0)
FLIGHT_HTTP_TIMEOUT = _env_float("FLIGHT_HTTP_TIMEOUT", 30.0)
HOTEL_HTTP_TIMEOUT = _env_float("HOTEL_HTTP_TIMEOUT", 30.0)

# Database timeouts
DB_QUERY_TIMEOUT = _env_float("DB_QUERY_TIMEOUT", 10.0)
DB_CONNECTION_TIMEOUT = _env_float("DB_CONNECTION_TIMEOUT", 15.0)

# Redis timeouts
REDIS_OPERATION_TIMEOUT = _env_float("REDIS_OPERATION_TIMEOUT", 5.0)
REDIS_CONNECTION_TIMEOUT = _env_float("REDIS_CONNECTION_TIMEOUT", 5.0)

# Graph execution timeout (overall conversation turn)
GRAPH_EXECUTION_TIMEOUT = _env_float("GRAPH_EXECUTION_TIMEOUT", 45.0)


# ---------------------------------------------------------------------------
# Core timeout helpers
# ---------------------------------------------------------------------------

async def with_timeout(
    coro,
    timeout: float,
    *,
    default: Any = None,
    operation_name: str = "operation",
    reraise: bool = False,
) -> Any:
    """
    Run an awaitable with a hard timeout.

    Production-grade behavior:
    - Catches `asyncio.TimeoutError` and returns `default` (or re-raises)
    - Catches `asyncio.CancelledError` separately (do not swallow)
    - Logs every timeout with the operation name and elapsed time
    - Never silently fails - always observable

    Args:
        coro: The awaitable to run (coroutine, future, or task).
        timeout: Maximum seconds to wait.
        default: Value to return on timeout.
        operation_name: Human-readable name for logging.
        reraise: If True, re-raise TimeoutError instead of returning default.

    Returns:
        Result of the coroutine, or `default` on timeout.

    Example:
        >>> result = await with_timeout(
        ...     llm.ainvoke([HumanMessage(content=prompt)]),
        ...     timeout=30.0,
        ...     operation_name="llm_chat",
        ...     default="I'm having trouble responding right now.",
        ... )
    """
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        elapsed = time.perf_counter() - start
        if elapsed > (timeout * 0.8):
            # Warn if we used >80% of the budget (slow but not failed)
            logger.warning(
                "Slow %s: %.2fs (budget %.2fs)",
                operation_name, elapsed, timeout,
            )
        return result
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        logger.error(
            "TIMEOUT in %s after %.2fs (budget %.2fs)",
            operation_name, elapsed, timeout,
        )
        if reraise:
            raise
        return default
    except asyncio.CancelledError:
        # Never swallow cancellation - propagate it
        logger.warning("Cancellation during %s", operation_name)
        raise
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error(
            "Error in %s after %.2fs: %s",
            operation_name, elapsed, e,
        )
        if reraise:
            raise
        return default


@asynccontextmanager
async def timeout_context(timeout: float, operation_name: str = "operation"):
    """
    Async context manager that enforces a timeout on its body.

    Useful when you need to wrap a block that contains multiple awaits
    and want a single overall budget.

    Example:
        >>> async with timeout_context(30.0, "graph_execution"):
        ...     async for event in graph.astream(state):
        ...         ...
    """
    start = time.perf_counter()
    try:
        # asyncio.timeout() is the modern API (Python 3.11+); fall back to
        # wait_for on older versions for portability.
        try:
            async with asyncio.timeout(timeout):
                yield
        except AttributeError:
            # Fallback for Python < 3.11
            task = asyncio.current_task()
            if task is None:
                yield
                return
            loop = asyncio.get_event_loop()
            handle = loop.call_later(
                timeout,
                task.cancel,
            )
            try:
                yield
            except asyncio.CancelledError:
                elapsed = time.perf_counter() - start
                logger.error(
                    "TIMEOUT in %s after %.2fs (budget %.2fs)",
                    operation_name, elapsed, timeout,
                )
                raise
            finally:
                handle.cancel()
    except TimeoutError:
        elapsed = time.perf_counter() - start
        logger.error(
            "TIMEOUT in %s after %.2fs (budget %.2fs)",
            operation_name, elapsed, timeout,
        )
        raise


def timeout_decorator(
    timeout: float,
    *,
    default: Any = None,
    operation_name: Optional[str] = None,
):
    """
    Decorator that adds a timeout to an async function.

    Args:
        timeout: Maximum seconds to wait.
        default: Value to return on timeout.
        operation_name: Name for logging (defaults to function name).

    Example:
        >>> @timeout_decorator(30.0, default="fallback response")
        ... async def call_llm(prompt: str) -> str:
        ...     return await llm.ainvoke([HumanMessage(content=prompt)])
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await with_timeout(
                func(*args, **kwargs),
                timeout=timeout,
                default=default,
                operation_name=op_name,
            )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Specialized helpers for common patterns
# ---------------------------------------------------------------------------

async def safe_llm_call(
    llm,
    messages,
    *,
    timeout: float = DEFAULT_LLM_TIMEOUT,
    default: Any = None,
    operation_name: str = "llm_call",
) -> Any:
    """
    Safely invoke an LLM with timeout protection.

    Args:
        llm: The LLM instance (must have `ainvoke`).
        messages: Messages to send to the LLM.
        timeout: Timeout in seconds.
        default: Fallback value on timeout/error.
        operation_name: Name for logging.

    Returns:
        LLM response or `default` on failure.
    """
    return await with_timeout(
        llm.ainvoke(messages),
        timeout=timeout,
        default=default,
        operation_name=operation_name,
    )


async def safe_http_call(
    coro,
    *,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    operation_name: str = "http_call",
    default: Any = None,
) -> Any:
    """
    Safely execute an HTTP call with timeout protection.

    Args:
        coro: The HTTP coroutine.
        timeout: Timeout in seconds.
        operation_name: Name for logging.
        default: Fallback value on timeout/error.

    Returns:
        HTTP response or `default` on failure.
    """
    return await with_timeout(
        coro,
        timeout=timeout,
        default=default,
        operation_name=operation_name,
    )


async def safe_db_call(
    coro,
    *,
    timeout: float = DB_QUERY_TIMEOUT,
    operation_name: str = "db_query",
    default: Any = None,
) -> Any:
    """
    Safely execute a database query with timeout protection.
    """
    return await with_timeout(
        coro,
        timeout=timeout,
        default=default,
        operation_name=operation_name,
    )


async def safe_redis_call(
    coro,
    *,
    timeout: float = REDIS_OPERATION_TIMEOUT,
    operation_name: str = "redis_op",
    default: Any = None,
) -> Any:
    """
    Safely execute a Redis operation with timeout protection.
    """
    return await with_timeout(
        coro,
        timeout=timeout,
        default=default,
        operation_name=operation_name,
    )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    # Constants
    "DEFAULT_LLM_TIMEOUT",
    "LONG_LLM_TIMEOUT",
    "SHORT_LLM_TIMEOUT",
    "DEFAULT_HTTP_TIMEOUT",
    "WEATHER_HTTP_TIMEOUT",
    "FLIGHT_HTTP_TIMEOUT",
    "HOTEL_HTTP_TIMEOUT",
    "DB_QUERY_TIMEOUT",
    "DB_CONNECTION_TIMEOUT",
    "REDIS_OPERATION_TIMEOUT",
    "REDIS_CONNECTION_TIMEOUT",
    "GRAPH_EXECUTION_TIMEOUT",
    # Helpers
    "with_timeout",
    "timeout_context",
    "timeout_decorator",
    "safe_llm_call",
    "safe_http_call",
    "safe_db_call",
    "safe_redis_call",
]
