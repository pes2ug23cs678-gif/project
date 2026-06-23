"""Shared retry helper for Groq / OpenAI-compatible API calls.

Usage
-----
from agents.retry import call_with_retry

response = call_with_retry(client.chat.completions.create, **kwargs)
"""

import time
import logging
import threading

logger = logging.getLogger(__name__)

# Global rate-limit cooldown — shared across all agents to prevent
# cascading retries when the Groq free tier is saturated.
_global_lock = threading.Lock()
_global_cooldown_until = 0.0  # timestamp


def _wait_for_global_cooldown():
    """Block until the global cooldown period has elapsed."""
    global _global_cooldown_until
    with _global_lock:
        remaining = _global_cooldown_until - time.time()
    if remaining > 0:
        logger.info("Global rate-limit cooldown: waiting %.1fs", remaining)
        time.sleep(remaining)


def _set_global_cooldown(seconds: float):
    """Set a global cooldown for all agents."""
    global _global_cooldown_until
    with _global_lock:
        new_until = time.time() + seconds
        if new_until > _global_cooldown_until:
            _global_cooldown_until = new_until


def call_with_retry(fn, *args, max_retries: int = 5, base_delay: float = 10.0, **kwargs):
    """Call *fn* with exponential back-off on rate-limit / server errors.

    Parameters
    ----------
    fn:
        Callable to invoke (e.g. ``client.chat.completions.create``).
    max_retries:
        Maximum number of retry attempts after the first failure.
    base_delay:
        Initial wait in seconds; doubles on each retry (1×, 2×, 4×…).
    *args / **kwargs:
        Forwarded verbatim to *fn*.

    Raises
    ------
    The last exception if all retries are exhausted.
    """
    delay = base_delay
    last_exc = None

    for attempt in range(max_retries + 1):
        # Respect global cooldown from other agents
        _wait_for_global_cooldown()

        try:
            return fn(*args, **kwargs)

        except Exception as exc:
            last_exc = exc
            exc_str = str(exc).lower()

            # Decide whether to retry
            is_retryable = (
                "rate_limit" in exc_str
                or "rate limit" in exc_str
                or "429" in exc_str
                or "overloaded" in exc_str
                or "503" in exc_str
                or "server_error" in exc_str
                or "service_unavailable" in exc_str
                or "timeout" in exc_str
            )

            if not is_retryable or attempt >= max_retries:
                raise  # non-retryable or retries exhausted

            # Try to extract Retry-After from the exception/response
            retry_after = _extract_retry_after(exc)
            
            # If the API says wait > 120s, it's a daily (TPD) limit, not per-minute.
            # Don't wait 30+ minutes — just raise so the caller can handle it.
            if retry_after > 120:
                logger.error(
                    "Groq daily token limit reached (wait=%ds). Raising immediately.",
                    int(retry_after),
                )
                raise

            # Cap wait time to 60 seconds max for per-minute rate limits
            wait_time = min(max(retry_after, delay) if retry_after else delay, 60)

            # Set global cooldown so other agents don't also hit the limit
            _set_global_cooldown(wait_time)

            logger.warning(
                "Groq API error (attempt %d/%d): %s. Waiting %.0fs…",
                attempt + 1, max_retries, str(exc)[:100], wait_time,
            )
            time.sleep(wait_time)
            delay = min(delay * 1.5, 60)  # cap at 60 seconds

    raise last_exc  # should never reach here


def _extract_retry_after(exc: Exception) -> float:
    """Try to extract Retry-After value from exception or its response."""
    try:
        # OpenAI library wraps the response in the exception
        if hasattr(exc, 'response') and exc.response is not None:
            retry_header = exc.response.headers.get('retry-after', '')
            if retry_header:
                return float(retry_header)
        # Check the error body for retry_after
        if hasattr(exc, 'body') and isinstance(exc.body, dict):
            error_info = exc.body.get('error', {})
            if isinstance(error_info, dict):
                msg = error_info.get('message', '')
                # Extract "try again in Xs" pattern
                import re
                m = re.search(r'try again in (\d+(?:\.\d+)?)\s*s', msg)
                if m:
                    return float(m.group(1))
    except Exception:
        pass
    return 0.0
