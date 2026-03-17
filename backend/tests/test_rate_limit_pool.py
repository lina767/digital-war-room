"""
Tests for RateLimitPool and TokenBucket.
"""

import threading
import time

from agents.rate_limit_pool import (
    RateLimitConfig,
    RateLimitPool,
    TokenBucket,
    get_rate_limit_pool,
)


class TestTokenBucket:
    def test_initial_burst(self):
        bucket = TokenBucket(rate=1.0, burst=3)
        for _ in range(3):
            assert bucket.acquire(timeout_s=0.01) is True

    def test_blocks_when_empty(self):
        bucket = TokenBucket(rate=1.0, burst=1)
        assert bucket.acquire(timeout_s=0.01) is True
        assert bucket.acquire(timeout_s=0.05) is False

    def test_refills_over_time(self):
        bucket = TokenBucket(rate=10.0, burst=1)
        assert bucket.acquire(timeout_s=0.01) is True
        time.sleep(0.15)
        assert bucket.acquire(timeout_s=0.01) is True

    def test_thread_safety(self):
        bucket = TokenBucket(rate=100.0, burst=10)
        results = []

        def worker():
            got = bucket.acquire(timeout_s=0.5)
            results.append(got)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)


class TestRateLimitPool:
    def test_acquire_unknown_api_uses_default(self):
        pool = RateLimitPool(config={})
        assert pool.acquire("unknown_api", timeout_s=0.1) is True

    def test_acquire_known_api(self):
        pool = RateLimitPool(config={"test": RateLimitConfig(tokens_per_second=10.0, max_burst=5)})
        for _ in range(5):
            assert pool.acquire("test", timeout_s=0.1) is True

    def test_rate_limiting_blocks(self):
        pool = RateLimitPool(config={"strict": RateLimitConfig(tokens_per_second=1.0, max_burst=1)})
        assert pool.acquire("strict", timeout_s=0.1) is True
        assert pool.acquire("strict", timeout_s=0.05) is False

    def test_singleton(self):
        p1 = get_rate_limit_pool()
        p2 = get_rate_limit_pool()
        assert p1 is p2
