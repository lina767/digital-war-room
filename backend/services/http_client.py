import asyncio
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("backend.http")


class HttpClient:
    """Shared async HTTP client with simple concurrency limits, retries and logging."""

    def __init__(self, timeout: float = 20.0, max_connections: int = 50, max_per_host: int = 8):
        limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_per_host)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True)
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._max_per_host = max_per_host

    def _get_semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._semaphores:
            self._semaphores[host] = asyncio.Semaphore(self._max_per_host)
        return self._semaphores[host]

    async def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 2,
        backoff_base: float = 0.5,
        **kwargs: Any,
    ) -> httpx.Response:
        parsed = urlparse(url)
        host = parsed.netloc or "default"
        sem = self._get_semaphore(host)

        attempt = 0
        backoff = backoff_base

        while True:
            attempt += 1
            async with sem:
                start = time.time()
                try:
                    resp = await self._client.request(method, url, **kwargs)
                    duration_ms = (time.time() - start) * 1000
                    logger.info("HTTP %s %s -> %s in %.1fms", method.upper(), url, resp.status_code, duration_ms)
                    resp.raise_for_status()
                    return resp
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    # Retry only on 5xx, everything andere sofort durchreichen
                    if status < 500 or attempt > retries:
                        logger.warning("HTTP error %s %s: %s", method.upper(), url, e)
                        raise
                    logger.warning(
                        "HTTP %s %s -> %s, retrying (attempt %s/%s)", method.upper(), url, status, attempt, retries
                    )
                except httpx.RequestError as e:
                    if attempt > retries:
                        logger.error("HTTP request failed %s %s: %s", method.upper(), url, e)
                        raise
                    logger.warning(
                        "HTTP request error %s %s (%s), retrying (attempt %s/%s)",
                        method.upper(),
                        url,
                        e,
                        attempt,
                        retries,
                    )
            await asyncio.sleep(backoff)
            backoff *= 2

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.request("GET", url, **kwargs)
        return resp.json()

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.request("POST", url, **kwargs)
        return resp.json()

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
