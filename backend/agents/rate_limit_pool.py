"""
RateLimitPool – Centralized token-bucket rate limiting across agents.

Prevents multiple agents from hitting the same external API's rate limit
simultaneously. Each API endpoint gets its own TokenBucket. Agents call
``pool.acquire("gdelt")`` before making an API request.
"""

import threading
import time
from typing import Dict, Optional

from pydantic import BaseModel


class RateLimitConfig(BaseModel):
    """Per-API rate limit configuration."""

    tokens_per_second: float = 1.0
    max_burst: int = 5
    timeout_s: float = 30.0


RATE_LIMITS: Dict[str, RateLimitConfig] = {
    "gdelt": RateLimitConfig(tokens_per_second=2.0, max_burst=5),
    "newsapi": RateLimitConfig(tokens_per_second=1.0, max_burst=3),
    "greynoise": RateLimitConfig(tokens_per_second=0.5, max_burst=2),
    "aisstream": RateLimitConfig(tokens_per_second=1.0, max_burst=3),
    "alpha_vantage": RateLimitConfig(tokens_per_second=0.2, max_burst=5),
    "etherscan": RateLimitConfig(tokens_per_second=0.2, max_burst=5),
    "overpass": RateLimitConfig(tokens_per_second=0.5, max_burst=2),
    "reddit": RateLimitConfig(tokens_per_second=1.0, max_burst=5),
    "fred": RateLimitConfig(tokens_per_second=1.0, max_burst=5),
    "eia": RateLimitConfig(tokens_per_second=1.0, max_burst=5),
}


class TokenBucket:
    """Leaky-bucket rate limiter. Thread-safe."""

    def __init__(self, rate: float, burst: int):
        self._rate = rate
        self._max_tokens = float(burst)
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout_s: float = 30.0) -> bool:
        """Block until a token is available, or return False on timeout."""
        deadline = time.monotonic() + timeout_s
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.1, 1.0 / max(self._rate, 0.01)))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
        self._last_refill = now


class RateLimitPool:
    """Global pool of TokenBuckets, one per API."""

    def __init__(self, config: Optional[Dict[str, RateLimitConfig]] = None):
        self._config = config or RATE_LIMITS
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, api_name: str) -> TokenBucket:
        with self._lock:
            if api_name not in self._buckets:
                cfg = self._config.get(api_name, RateLimitConfig())
                self._buckets[api_name] = TokenBucket(
                    rate=cfg.tokens_per_second,
                    burst=cfg.max_burst,
                )
            return self._buckets[api_name]

    def acquire(self, api_name: str, timeout_s: Optional[float] = None) -> bool:
        """Acquire a rate-limit token for the given API. Blocks until available.

        Returns False only if timeout is exceeded.
        """
        bucket = self._get_bucket(api_name)
        cfg = self._config.get(api_name, RateLimitConfig())
        t = timeout_s if timeout_s is not None else cfg.timeout_s
        return bucket.acquire(timeout_s=t)


_global_pool: Optional[RateLimitPool] = None


def get_rate_limit_pool() -> RateLimitPool:
    """Return the global RateLimitPool singleton."""
    global _global_pool
    if _global_pool is None:
        _global_pool = RateLimitPool()
    return _global_pool
