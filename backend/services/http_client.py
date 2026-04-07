import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

import httpx
from services.privacy_sanitize import redact_url

logger = logging.getLogger("backend.http")


class CircuitOpenError(RuntimeError):
    """Raised when a service circuit breaker is open."""


@dataclass
class CircuitBreakerState:
    consecutive_failures: int = 0
    open_until_ts: float = 0.0


class HttpClient:
    """Shared async HTTP client with retries, bulkheads, circuit breaker and logging."""

    def __init__(self, timeout: float = 20.0, max_connections: int = 50, max_per_host: int = 8):
        limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_per_host)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True)
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._circuits: Dict[str, CircuitBreakerState] = {}
        self._max_per_host = max_per_host
        self._default_failure_threshold = max(1, int(os.getenv("HTTP_CIRCUIT_FAILURE_THRESHOLD", "5")))
        self._default_recovery_timeout_sec = max(1.0, float(os.getenv("HTTP_CIRCUIT_RECOVERY_TIMEOUT_SEC", "30")))
        self._default_backoff_jitter_ratio = min(
            1.0,
            max(0.0, float(os.getenv("HTTP_RETRY_JITTER_RATIO", "0.25"))),
        )

    def _get_semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._semaphores:
            self._semaphores[host] = asyncio.Semaphore(self._max_per_host)
        return self._semaphores[host]

    def _is_circuit_open(self, circuit_key: str) -> bool:
        state = self._circuits.get(circuit_key)
        if not state:
            return False
        now = time.time()
        return state.open_until_ts > now

    def _record_success(self, circuit_key: str) -> None:
        state = self._circuits.get(circuit_key)
        if state:
            state.consecutive_failures = 0
            state.open_until_ts = 0.0

    def _record_failure(self, circuit_key: str, *, failure_threshold: int, recovery_timeout_sec: float) -> None:
        state = self._circuits.setdefault(circuit_key, CircuitBreakerState())
        state.consecutive_failures += 1
        if state.consecutive_failures >= max(1, failure_threshold):
            state.open_until_ts = time.time() + max(1.0, recovery_timeout_sec)
            logger.warning(
                "Circuit opened for %s after %d failures (open %.1fs)",
                circuit_key,
                state.consecutive_failures,
                recovery_timeout_sec,
            )

    async def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 2,
        backoff_base: float = 0.5,
        service_name: Optional[str] = None,
        retry_statuses: Optional[Set[int]] = None,
        circuit_breaker_enabled: bool = True,
        failure_threshold: Optional[int] = None,
        recovery_timeout_sec: Optional[float] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        parsed = urlparse(url)
        host = parsed.netloc or "default"
        sem = self._get_semaphore(host)
        circuit_key = (service_name or parsed.hostname or host or "default").lower()
        retryable_statuses = retry_statuses or {429, 500, 502, 503, 504}
        threshold = failure_threshold if failure_threshold is not None else self._default_failure_threshold
        recovery = recovery_timeout_sec if recovery_timeout_sec is not None else self._default_recovery_timeout_sec

        attempt = 0
        backoff = backoff_base

        while True:
            attempt += 1
            if circuit_breaker_enabled and self._is_circuit_open(circuit_key):
                safe_url = redact_url(url)
                logger.warning("Circuit open for %s - skipping %s %s", circuit_key, method.upper(), safe_url)
                raise CircuitOpenError(f"circuit_open:{circuit_key}")
            async with sem:
                start = time.time()
                try:
                    resp = await self._client.request(method, url, **kwargs)
                    duration_ms = (time.time() - start) * 1000
                    safe_url = redact_url(url)
                    logger.info("HTTP %s %s -> %s in %.1fms", method.upper(), safe_url, resp.status_code, duration_ms)
                    resp.raise_for_status()
                    if circuit_breaker_enabled:
                        self._record_success(circuit_key)
                    return resp
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    safe_url = redact_url(url)
                    parsed_host = (parsed.hostname or "").lower()
                    # Retry only on 5xx, everything andere sofort durchreichen
                    should_retry = status in retryable_statuses and attempt <= retries
                    if not should_retry:
                        if status == 404 and parsed_host == "internetdb.shodan.io":
                            # InternetDB returns 404 for IPs without data; this is expected.
                            logger.debug("HTTP expected 404 %s %s", method.upper(), safe_url)
                        else:
                            logger.warning("HTTP error %s %s: %s", method.upper(), safe_url, e)
                        if circuit_breaker_enabled and not (status == 404 and parsed_host == "internetdb.shodan.io"):
                            self._record_failure(
                                circuit_key,
                                failure_threshold=threshold,
                                recovery_timeout_sec=recovery,
                            )
                        raise
                    logger.warning(
                        "HTTP %s %s -> %s, retrying (attempt %s/%s)",
                        method.upper(),
                        safe_url,
                        status,
                        attempt,
                        retries,
                    )
                except httpx.RequestError as e:
                    safe_url = redact_url(url)
                    if attempt > retries:
                        logger.error("HTTP request failed %s %s: %s", method.upper(), safe_url, e)
                        if circuit_breaker_enabled:
                            self._record_failure(
                                circuit_key,
                                failure_threshold=threshold,
                                recovery_timeout_sec=recovery,
                            )
                        raise
                    logger.warning(
                        "HTTP request error %s %s (%s), retrying (attempt %s/%s)",
                        method.upper(),
                        safe_url,
                        e,
                        attempt,
                        retries,
                    )
            jitter_max = max(0.0, backoff * self._default_backoff_jitter_ratio)
            await asyncio.sleep(backoff + random.uniform(0.0, jitter_max))
            backoff *= 2

    async def get_json(self, url: str, *, fallback: Any = None, **kwargs: Any) -> Any:
        try:
            resp = await self.request("GET", url, **kwargs)
            return resp.json()
        except Exception:
            if fallback is not None:
                return fallback
            raise

    async def post_json(self, url: str, *, fallback: Any = None, **kwargs: Any) -> Any:
        try:
            resp = await self.request("POST", url, **kwargs)
            return resp.json()
        except Exception:
            if fallback is not None:
                return fallback
            raise

    async def aclose(self) -> None:
        await self._client.aclose()


_client: Optional[HttpClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_http_client() -> HttpClient:
    """Return process-wide shared HttpClient instance, recreating if event loop changed."""
    global _client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    # Client exists but event loop changed -> recreate.
    if _client is not None and _client_loop is not current_loop:
        # Do not await old client close here (old loop may be gone).
        _client = None
        _client_loop = None

    if _client is None:
        _client = HttpClient()
        _client_loop = current_loop
    return _client


async def close_http_client() -> None:
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None
