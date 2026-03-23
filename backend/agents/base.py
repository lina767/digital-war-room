"""
BaseAgent – Abstract base class for all intelligence agents.

Provides: typed result wrapping, circuit breaker, content hashing,
structured metrics, and integration with AgentStateStore.
"""

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict, Generic, List, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .utils import AgentMetadata, SourceResult, utc_now_iso

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseAgentResult")

_AGENT_EXEC_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-safe")


# ---------------------------------------------------------------------------
# Typed result models
# ---------------------------------------------------------------------------


class BaseAgentResult(BaseModel):
    """Common base fields shared by every agent result contract."""

    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)

    schema_version: int = 1
    conflict: str = ""
    score: float = 0.0
    summary: str = ""
    content_hash: str = ""
    _meta: Optional[Dict[str, Any]] = None
    # Data-quality roll-up (see agents/dq_contract.py). Populated explicitly or via sync_agent_quality_from_meta.
    dq_confidence: float = Field(0.0, ge=0.0, le=100.0)
    data_freshness: Literal["live", "recent", "stale", "unavailable"] = "unavailable"
    source_count: int = Field(0, ge=0)
    fallback_used: bool = False
    error_summary: Optional[str] = None
    provenance_refs: List[str] = Field(default_factory=list)


class AgentMetrics(BaseModel):
    """Structured execution metrics collected by run_safe."""

    latency_ms: int = 0
    source_count: int = 0
    api_calls_made: int = 0
    sources: List[SourceResult] = Field(default_factory=list)


class CircuitBreakerState(BaseModel):
    """Per-agent circuit breaker persisted across cycles."""

    consecutive_failures: int = 0
    is_open: bool = False
    last_failure_at: Optional[str] = None
    reopen_after_cycles: int = 3
    cycles_skipped: int = 0


class AgentResult(BaseModel, Generic[T]):
    """Wrapper around a typed agent result with metadata and metrics."""

    data: Any  # typed T – kept as Any for Pydantic v2 Generic compat
    meta: Optional[AgentMetadata] = None
    content_hash: str = ""
    metrics: AgentMetrics = Field(default_factory=AgentMetrics)
    error: Optional[str] = None
    is_fallback: bool = False


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class BaseAgent(ABC, Generic[T]):
    """Abstract base for all intelligence agents.

    Subclasses implement ``run(conflict)`` returning a typed result T.
    ``run_safe`` wraps ``run`` with timeout, circuit breaker, content hash,
    metrics, and state-store integration.
    """

    name: str = ""
    timeout: float = 75.0
    result_type: Type[T] = BaseAgentResult  # type: ignore[assignment]
    fallback_data: Optional[T] = None

    def __init__(self) -> None:
        self._circuit_breaker = CircuitBreakerState()

    # -- Subclass interface --------------------------------------------------

    @abstractmethod
    def run(self, conflict: str) -> T:
        """Execute the agent's collection logic. Must return a typed result."""
        ...

    def get_fallback(self, conflict: str) -> T:
        """Return a safe fallback result. Override for richer defaults."""
        if self.fallback_data is not None:
            return self.fallback_data
        return self.result_type(conflict=conflict)  # type: ignore[call-arg]

    # -- Public entry point --------------------------------------------------

    def run_safe(self, conflict: str, *, store: Optional[Any] = None) -> AgentResult:
        """Execute with circuit breaker, timeout, hashing, and metrics.

        Args:
            conflict: conflict identifier (e.g. "Iran")
            store: optional AgentStateStore for delta tracking
        """
        cb = self._circuit_breaker
        start = time.perf_counter()

        # 1. Circuit breaker – open → skip immediately
        if cb.is_open:
            if cb.cycles_skipped < cb.reopen_after_cycles:
                cb.cycles_skipped += 1
                logger.info(
                    "[%s] circuit breaker OPEN – skipping (cycle %d/%d)",
                    self.name,
                    cb.cycles_skipped,
                    cb.reopen_after_cycles,
                )
                fallback = self.get_fallback(conflict)
                return self._wrap_result(fallback, start, is_fallback=True, error="circuit breaker open")
            # Half-open: attempt one run
            logger.info("[%s] circuit breaker HALF-OPEN – attempting", self.name)

        # 2. Timeout-protected run
        try:
            future = _AGENT_EXEC_POOL.submit(self.run, conflict)
            result = future.result(timeout=self.timeout)
        except FuturesTimeoutError:
            logger.warning("[%s] timed out after %.0fs", self.name, self.timeout)
            self._record_failure(cb)
            fallback = self.get_fallback(conflict)
            return self._wrap_result(fallback, start, is_fallback=True, error=f"timeout after {self.timeout}s")
        except Exception as exc:
            logger.warning("[%s] failed: %s", self.name, exc)
            self._record_failure(cb)
            fallback = self.get_fallback(conflict)
            return self._wrap_result(fallback, start, is_fallback=True, error=str(exc))

        # 3. Success → reset circuit breaker
        self._record_success(cb)

        # 4. Build wrapped result with hash + metrics
        agent_result = self._wrap_result(result, start, is_fallback=False)

        # 5. Store in AgentStateStore for delta comparison
        if store is not None:
            try:
                store.set_result(conflict, self.name, agent_result, time.time())
                store.set_content_hash(conflict, self.name, agent_result.content_hash)
                store.set_circuit_breaker(self.name, cb)
            except Exception as e:
                logger.debug("[%s] state store write failed: %s", self.name, e)

        return agent_result

    # -- Backwards-compat: return plain dict like existing agents -------------

    def run_safe_dict(self, conflict: str, *, store: Optional[Any] = None) -> Dict[str, Any]:
        """Like run_safe but returns a plain dict matching legacy API format."""
        ar = self.run_safe(conflict, store=store)
        if isinstance(ar.data, BaseModel):
            data = ar.data.model_dump(mode="json")
        elif isinstance(ar.data, dict):
            data = ar.data
        else:
            data = {"_raw": ar.data}
        if ar.meta:
            data["_meta"] = ar.meta.model_dump(mode="json")
        return data

    # -- Internal helpers ----------------------------------------------------

    def _wrap_result(self, data: Any, start: float, *, is_fallback: bool, error: Optional[str] = None) -> AgentResult:
        latency_ms = int((time.perf_counter() - start) * 1000)
        content_hash = self._compute_hash(data)

        sources: List[SourceResult] = []
        meta_dict = None
        if isinstance(data, BaseModel):
            meta_dict = getattr(data, "_meta", None)
        elif isinstance(data, dict):
            meta_dict = data.get("_meta")

        meta = None
        if isinstance(meta_dict, dict):
            try:
                meta = AgentMetadata(**meta_dict)
                sources = meta.sources
            except Exception:
                pass

        metrics = AgentMetrics(
            latency_ms=latency_ms,
            source_count=len(sources),
            api_calls_made=0,
            sources=sources,
        )
        return AgentResult(
            data=data,
            meta=meta,
            content_hash=content_hash,
            metrics=metrics,
            error=error,
            is_fallback=is_fallback,
        )

    @staticmethod
    def _compute_hash(data: Any) -> str:
        """SHA-256 content hash for delta comparison between cycles."""
        try:
            if isinstance(data, BaseModel):
                raw = data.model_dump_json(exclude={"content_hash", "_meta"})
            elif isinstance(data, dict):
                filtered = {k: v for k, v in data.items() if k not in ("content_hash", "_meta")}
                raw = json.dumps(filtered, sort_keys=True, default=str)
            else:
                raw = str(data)
            return hashlib.sha256(raw.encode()).hexdigest()[:16]
        except Exception:
            return ""

    @staticmethod
    def _record_failure(cb: CircuitBreakerState) -> None:
        cb.consecutive_failures += 1
        cb.last_failure_at = utc_now_iso()
        if cb.consecutive_failures >= 3 and not cb.is_open:
            cb.is_open = True
            cb.cycles_skipped = 0
            logger.warning("Circuit breaker OPENED after %d consecutive failures", cb.consecutive_failures)

    @staticmethod
    def _record_success(cb: CircuitBreakerState) -> None:
        was_half_open = cb.is_open and cb.cycles_skipped >= cb.reopen_after_cycles
        cb.consecutive_failures = 0
        cb.is_open = False
        cb.cycles_skipped = 0
        cb.last_failure_at = None
        if was_half_open:
            logger.info("Circuit breaker CLOSED (half-open attempt succeeded)")
