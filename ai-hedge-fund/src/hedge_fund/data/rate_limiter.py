"""Token-bucket rate limiter for data providers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    """Token bucket for a single provider."""

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def acquire(self) -> bool:
        """Try to consume one token. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    def wait_time(self) -> float:
        """Seconds until a token becomes available."""
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.refill_rate


class RateLimiter:
    """Per-provider rate limiting using token buckets."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def configure(self, provider: str, calls_per_minute: int) -> None:
        """Set rate limit for a provider."""
        capacity = float(calls_per_minute)
        refill_rate = calls_per_minute / 60.0
        self._buckets[provider] = _Bucket(capacity=capacity, refill_rate=refill_rate)

    def acquire(self, provider: str) -> bool:
        """Try to acquire a rate limit token for the provider.
        Returns True if the call is allowed. If no bucket is configured, always allows."""
        bucket = self._buckets.get(provider)
        if bucket is None:
            return True
        return bucket.acquire()

    def wait_time(self, provider: str) -> float:
        """How long to wait before next call is allowed."""
        bucket = self._buckets.get(provider)
        if bucket is None:
            return 0.0
        return bucket.wait_time()

    def status(self) -> dict[str, dict]:
        """Return rate limit status for all providers."""
        return {
            name: {
                "tokens_available": round(bucket.tokens, 1),
                "capacity": bucket.capacity,
                "refill_rate_per_sec": round(bucket.refill_rate, 2),
            }
            for name, bucket in self._buckets.items()
        }
