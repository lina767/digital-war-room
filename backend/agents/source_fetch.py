"""
SourceFetch – context manager for per-source HTTP fetches with timing, error capture,
and health reporting. Use around each external API call in agents.
"""
import asyncio
import logging
import time
from typing import Optional

from .utils import SourceResult, utc_now_iso

logger = logging.getLogger(__name__)


class SourceFetch:
    """
    Async context manager wrapping a single external fetch. Records duration,
    status, and optional record_count; reports to HealthRegistry on exit.
    """

    def __init__(self, source_name: str, agent_name: str, retries: int = 2):
        self.source_name = source_name
        self.agent_name = agent_name
        self.retries = retries
        self._start: Optional[float] = None
        self._record_count: Optional[int] = None
        self._cached: bool = False
        self._error: Optional[str] = None
        self._result: Optional[SourceResult] = None
        self._exception: Optional[BaseException] = None

    async def __aenter__(self) -> "SourceFetch":
        self._start = time.perf_counter()
        self._record_count = None
        self._cached = False
        self._error = None
        self._result = None
        self._exception = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = None
        if self._start is not None:
            duration_ms = int((time.perf_counter() - self._start) * 1000)
        fetched_at = utc_now_iso()
        status = "ok"
        error_msg = self._error
        if exc_val is not None:
            self._exception = exc_val
            status = "error"
            error_msg = str(exc_val) if not error_msg else error_msg
        elif self._error is not None:
            status = "error"
            error_msg = self._error
        self._result = SourceResult(
            name=self.source_name,
            status=status,
            fetched_at=fetched_at,
            duration_ms=duration_ms,
            record_count=self._record_count,
            error=error_msg,
            cached=self._cached,
        )
        try:
            from .health_registry import get_health_registry
            reg = get_health_registry()
            if reg is not None:
                reg.record_result(self.source_name, self.agent_name, self._result)
        except Exception as e:
            logger.debug("HealthRegistry record_result skipped: %s", e)
        return True  # suppress exception so caller can check result()

    def set_record_count(self, count: int) -> None:
        self._record_count = count

    def set_cached(self, cached: bool = True) -> None:
        self._cached = cached

    def set_error(self, message: str) -> None:
        self._error = message

    def result(self) -> SourceResult:
        if self._result is None:
            return SourceResult(
                name=self.source_name,
                status="error",
                error="no result captured",
            )
        return self._result
