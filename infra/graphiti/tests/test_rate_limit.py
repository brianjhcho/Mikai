"""
Tests for sidecar.rate_limit — async token-bucket rate limiter.

Follows the same "Humble Object" / fakes-over-mocks pattern used in
test_mcp_ingest.py: injected fake clock and fake sleep make timing
deterministic without real asyncio.sleep calls.

All tests use asyncio_mode = auto (set in pytest.ini).
"""

from __future__ import annotations

import asyncio
from typing import List

import pytest

from sidecar.rate_limit import TokenBucket, _BUCKETS, bucket_for


# ── Fake clock / sleep infrastructure ────────────────────────────────────────


class FakeClock:
    """Monotonically-advancing fake clock. Advance with .tick(seconds)."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def tick(self, seconds: float) -> None:
        self._now += seconds


class FakeSleep:
    """Records all sleep durations; advancing the clock is the caller's job."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.calls: List[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        # Advance time so the next _refill() sees enough tokens.
        self._clock.tick(seconds)


def make_bucket(
    rate_per_minute: int,
    burst: int | None = None,
    *,
    clock_start: float = 0.0,
) -> tuple[TokenBucket, FakeClock, FakeSleep]:
    clock = FakeClock(start=clock_start)
    sleep = FakeSleep(clock)
    bucket = TokenBucket(rate_per_minute=rate_per_minute, burst=burst, clock=clock, sleep=sleep)
    return bucket, clock, sleep


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestTokenBucket:
    async def test_fresh_bucket_first_acquire_is_immediate(self):
        """Test 1: Fresh bucket — first acquire is immediate (no sleep)."""
        bucket, _clock, sleep = make_bucket(rate_per_minute=60)

        await bucket.acquire()

        assert sleep.calls == [], "No sleep expected for a full bucket"

    async def test_empty_bucket_blocks_until_refill(self):
        """Test 2: Bucket empty — acquire blocks until refill."""
        bucket, clock, sleep = make_bucket(rate_per_minute=60, burst=1)

        # Drain the single token.
        await bucket.acquire()
        assert sleep.calls == []

        # Now the bucket is empty; next acquire should sleep.
        await bucket.acquire()

        assert len(sleep.calls) == 1
        assert sleep.calls[0] > 0

    async def test_refill_math_rate60_burst60_advance30s(self):
        """Test 3: rate=60, burst=60, advance clock 30s, acquire 30 tokens with no sleep."""
        bucket, clock, sleep = make_bucket(rate_per_minute=60, burst=60)

        # Drain all 60 tokens.
        for _ in range(60):
            await bucket.acquire()
        assert sleep.calls == [], "Initial 60 tokens should require no sleep"

        # Advance 30 seconds → 30 new tokens (rate = 1/s).
        clock.tick(30)

        # Acquire 30 should complete without sleep.
        for _ in range(30):
            await bucket.acquire()

        assert sleep.calls == [], "30 s elapsed should provide exactly 30 tokens"

    async def test_burst_respected_acquire_burst_then_wait(self):
        """Test 4: rate=60, burst=100, can acquire 100 immediately then must wait."""
        bucket, _clock, sleep = make_bucket(rate_per_minute=60, burst=100)

        # First 100 acquires should be immediate.
        for _ in range(100):
            await bucket.acquire()

        assert sleep.calls == [], "burst=100 should allow 100 immediate acquires"

        # 101st requires waiting.
        await bucket.acquire()
        assert len(sleep.calls) == 1

    async def test_concurrent_acquirers_second_waits(self):
        """Test 5: Two coroutines acquire serially; second waits."""
        bucket, clock, sleep = make_bucket(rate_per_minute=60, burst=1)

        order: list[str] = []

        async def first():
            await bucket.acquire()
            order.append("first")

        async def second():
            await bucket.acquire()
            order.append("second")

        await asyncio.gather(first(), second())

        # Both must complete.
        assert "first" in order
        assert "second" in order
        # Second must have waited.
        assert len(sleep.calls) >= 1

    async def test_cancellation_does_not_leak_tokens(self):
        """Test 6: Cancellation during sleep does not leak tokens."""
        bucket, clock, sleep = make_bucket(rate_per_minute=60, burst=1)

        # Drain the token.
        await bucket.acquire()

        # Replace sleep with one that cancels itself.
        cancel_called = False

        async def cancelling_sleep(seconds: float) -> None:
            nonlocal cancel_called
            cancel_called = True
            raise asyncio.CancelledError()

        bucket._sleep = cancelling_sleep

        with pytest.raises(asyncio.CancelledError):
            await bucket.acquire()

        # Token was not decremented (we were still sleeping).
        assert cancel_called
        # After advancing time, a new acquire should work without sleep.
        clock.tick(60)
        bucket._sleep = sleep  # restore
        await bucket.acquire()
        # The successful acquire should not have needed sleep (token regenerated).
        assert sleep.calls == []

    async def test_n_greater_than_burst_raises_value_error(self):
        """Test 7: n > burst raises ValueError."""
        bucket, _clock, _sleep = make_bucket(rate_per_minute=60, burst=10)

        with pytest.raises(ValueError, match="burst capacity"):
            await bucket.acquire(n=11)

    async def test_bucket_for_returns_same_instance(self):
        """Test 8: bucket_for('x') returns same instance across two calls."""
        _BUCKETS.clear()

        b1 = bucket_for("test_singleton")
        b2 = bucket_for("test_singleton")

        assert b1 is b2

    async def test_bucket_for_reads_env_var_overrides(self, monkeypatch):
        """Test 9: bucket_for reads env var overrides (monkeypatch env)."""
        _BUCKETS.clear()

        monkeypatch.setenv("MIKAI_RATELIMIT_MYSERVICE_RPM", "120")
        monkeypatch.setenv("MIKAI_RATELIMIT_MYSERVICE_BURST", "200")

        b = bucket_for("myservice")

        assert b._burst == 200
        # rate_per_second = 120 / 60 = 2.0
        assert abs(b._rate_per_second - 2.0) < 1e-9

    async def test_bucket_for_default_rates(self, monkeypatch):
        """Test 10: bucket_for default rates: deepseek/voyage=60 rpm, others=30 rpm."""
        _BUCKETS.clear()

        # Remove any env overrides to get true defaults.
        monkeypatch.delenv("MIKAI_RATELIMIT_DEEPSEEK_RPM", raising=False)
        monkeypatch.delenv("MIKAI_RATELIMIT_DEEPSEEK_BURST", raising=False)
        monkeypatch.delenv("MIKAI_RATELIMIT_VOYAGE_RPM", raising=False)
        monkeypatch.delenv("MIKAI_RATELIMIT_VOYAGE_BURST", raising=False)
        monkeypatch.delenv("MIKAI_RATELIMIT_OTHER_RPM", raising=False)
        monkeypatch.delenv("MIKAI_RATELIMIT_OTHER_BURST", raising=False)

        deepseek = bucket_for("deepseek")
        voyage = bucket_for("voyage")
        other = bucket_for("other")

        # deepseek: 60 rpm → 1.0 token/s, burst=60
        assert deepseek._burst == 60
        assert abs(deepseek._rate_per_second - 1.0) < 1e-9

        # voyage: 60 rpm → 1.0 token/s, burst=60
        assert voyage._burst == 60
        assert abs(voyage._rate_per_second - 1.0) < 1e-9

        # other: 30 rpm → 0.5 token/s, burst=30
        assert other._burst == 30
        assert abs(other._rate_per_second - 0.5) < 1e-9
