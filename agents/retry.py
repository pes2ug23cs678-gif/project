"""Shared retry helper for Groq / OpenAI-compatible API calls.

Usage
-----
from agents.retry import call_with_retry

response = call_with_retry(client.chat.completions.create, **kwargs)
"""

import time
import logging

logger = logging.getLogger(__name__)

# HTTP status codes / error codes that warrant a retry
_RETRYABLE_CODES = {"rate_limit_exceeded", "overloaded", "server_error"}


def call_with_retry(fn, *args, max_retries: int = 4, base_delay: float = 8.0, **kwargs):
    """Call *fn* with exponential back-off on rate-limit / server errors.

    Parameters
    ----------
    fn:
        Callable to invoke (e.g. ``client.chat.completions.create``).
    max_retries:
        Maximum number of retry attempts after the first failure.
    base_delay:
        Initial wait in seconds; doubles on each retry (1×, 2×, 4×, 8×…).
    *args / **kwargs:
        Forwarded verbatim to *fn*.

    Raises
    ------
    The last exception if all retries are exhausted.
    """
    delay = base_delay
    last_exc = None

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)

        except Exception as exc:
            last_exc = exc
            exc_str = str(exc).lower()

            # Decide whether to retry
            is_rate_limit = (
                "rate_limit" in exc_str
                or "rate limit" in exc_str
                or "429" in exc_str
                or "overloaded" in exc_str
                or "503" in exc_str
                or any(c in exc_str for c in _RETRYABLE_CODES)
            )

            if not is_rate_limit or attempt >= max_retries:
                raise  # non-retryable or retries exhausted

            logger.warning(
                "Groq rate limit hit (attempt %d/%d). Waiting %.0fs before retry…",
                attempt + 1, max_retries, delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 120)  # cap at 2 minutes

    raise last_exc  # should never reach here
