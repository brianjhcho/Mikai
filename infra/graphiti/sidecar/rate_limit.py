"""
Async token-bucket rate limiter for the MIKAI Graphiti sidecar.

References O-041. Callers on the add_episode path should call
``await bucket_for('deepseek').acquire()`` before invoking graphiti so that
DeepSeek and Voyage API calls stay within their per-minute limits.

TODO(lead): wire bucket_for('deepseek').acquire() into mcp_ingest.py and
sync.py once Phase A lands. grep TODO(lead) to find all wiring points.

Usage::

    from sidecar.rate_limit import bucket_for

    async def ingest(episode):
        await bucket_for('deepseek').acquire()
        await graphiti.add_episode(**episode)

Named buckets are singletons keyed by name. Override rates via env vars:

    MIKAI_RATELIMIT_DEEPSEEK_RPM=120
    MIKAI_RATELIMIT_DEEPSEEK_BURST=200
"""

from __future__ import annotations

import asyncio
import os
import time as _time_module
from typing import Callable


class TokenBucket:
    """Async token bucket with injected clock and sleep for testability.

    Args:
        rate_per_minute: Tokens added per minute (continuous refill).
        burst: Maximum token capacity. Defaults to ``rate_per_minute``.
        clock: Callable returning monotonic time in seconds. Defaults to
            ``time.monotonic``.
        sleep: Async callable accepting seconds to sleep. Defaults to
            ``asyncio.sleep``.
    """

    def __init__(
        self,
        rate_per_minute: int,
        burst: int | None = None,
        *,
        clock: Callable[[], float] = _time_module.monotonic,
        sleep: Callable[[float], object] = asyncio.sleep,
    ) -> None:
        self._rate_per_second: float = rate_per_minute / 60.0
        self._burst: int = burst if burst is not None else rate_per_minute
        self._clock = clock
        self._sleep = sleep

        self._tokens: float = float(self._burst)
        self._last_refill: float = self._clock()
        self._lock: asyncio.Lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed wall time. Must be called under lock."""
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                self._burst,
                self._tokens + elapsed * self._rate_per_second,
            )
            self._last_refill = now

    async def acquire(self, n: int = 1) -> None:
        """Wait until ``n`` tokens are available, then consume them.

        Args:
            n: Number of tokens to acquire. Must be <= burst.

        Raises:
            ValueError: If ``n > burst`` (request can never be satisfied).
        """
        if n > self._burst:
            raise ValueError(
                f"Requested {n} tokens but burst capacity is {self._burst}; "
                "this acquire() can never be satisfied."
            )

        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= n:
                    self._tokens -= n
                    return
                # Calculate how long until enough tokens accumulate.
                deficit = n - self._tokens
                wait_seconds = deficit / self._rate_per_second

            # Sleep outside the lock so other coroutines can check.
            await self._sleep(wait_seconds)


# ── Named-bucket registry ─────────────────────────────────────────────────────

_BUCKETS: dict[str, TokenBucket] = {}

_DEFAULT_RPM: dict[str, int] = {
    "deepseek": 60,
    "voyage": 60,
}
_FALLBACK_RPM = 30


def bucket_for(name: str) -> TokenBucket:
    """Return (or create) the singleton ``TokenBucket`` for *name*.

    Configuration is read from environment variables on first call:

    - ``MIKAI_RATELIMIT_<NAME_UPPER>_RPM`` — tokens per minute (default: 60
      for ``deepseek``/``voyage``, 30 for everything else)
    - ``MIKAI_RATELIMIT_<NAME_UPPER>_BURST`` — burst capacity (default: rpm)

    The bucket is cached in the module-level ``_BUCKETS`` registry. Subsequent
    calls with the same name return the same instance.
    """
    if name in _BUCKETS:
        return _BUCKETS[name]

    upper = name.upper()
    default_rpm = _DEFAULT_RPM.get(name, _FALLBACK_RPM)

    rpm_env = os.environ.get(f"MIKAI_RATELIMIT_{upper}_RPM")
    burst_env = os.environ.get(f"MIKAI_RATELIMIT_{upper}_BURST")

    rpm = int(rpm_env) if rpm_env is not None else default_rpm
    burst = int(burst_env) if burst_env is not None else rpm

    bucket = TokenBucket(rate_per_minute=rpm, burst=burst)
    _BUCKETS[name] = bucket
    return bucket
