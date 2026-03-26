"""
HealthRegistry – in-memory per-source health tracking across runs.
Stores last N results per source, computes availability and latency, detects circuit-open state.
"""

import logging
import os
import threading
from collections import deque
from typing import Any, Dict, List, Optional

from .utils import SourceResult

logger = logging.getLogger(__name__)

# Default ring buffer size per source
DEFAULT_HISTORY_SIZE = 10
# Consecutive failures before marking source as "down" (circuit open)
CIRCUIT_OPEN_THRESHOLD = 3
_ALLOWED_OVERRIDE_STATUSES = {"ok", "degraded", "down"}


def _load_source_status_overrides() -> Dict[str, str]:
    """
    Parse SOURCE_STATUS_OVERRIDES from env.
    Format: "Source A=down;Source B=degraded;Source C=ok"
    """
    raw = (os.getenv("SOURCE_STATUS_OVERRIDES") or "").strip()
    if not raw:
        return {}
    overrides: Dict[str, str] = {}
    for part in raw.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, status = item.split("=", 1)
        source_name = name.strip()
        state = status.strip().lower()
        if not source_name or state not in _ALLOWED_OVERRIDE_STATUSES:
            continue
        overrides[source_name] = state
    return overrides


class HealthRegistry:
    """
    Thread-safe registry of per-source fetch results. One key per (source_name, agent_name)
    so the same source used by different agents is tracked separately.
    """

    def __init__(self, history_size: int = DEFAULT_HISTORY_SIZE):
        self._history_size = history_size
        self._data: Dict[str, deque] = {}  # key = f"{source_name}|{agent_name}" -> deque of result dicts
        self._lock = threading.Lock()

    def _key(self, source_name: str, agent_name: str) -> str:
        return f"{source_name}|{agent_name}"

    def record_result(self, source_name: str, agent_name: str, result: SourceResult) -> None:
        key = self._key(source_name, agent_name)
        entry = {
            "source": source_name,
            "agent": agent_name,
            "status": result.status,
            "fetched_at": result.fetched_at,
            "duration_ms": result.duration_ms,
            "record_count": result.record_count,
            "error": result.error,
        }
        with self._lock:
            if key not in self._data:
                self._data[key] = deque(maxlen=self._history_size)
            self._data[key].append(entry)

    def get_health_report(self) -> Dict[str, Any]:
        """
        Returns a report suitable for GET /api/agents/health:
        - sources: list of per-source entries (availability_pct, avg_latency_ms, status, circuit_open, last_error, last_results)
        - summary: total sources, degraded count, down count
        """
        with self._lock:
            overrides = _load_source_status_overrides()
            sources: List[Dict[str, Any]] = []
            for key, history in list(self._data.items()):
                if not history:
                    continue
                parts = key.split("|", 1)
                source_name = parts[0]
                agent_name = parts[1] if len(parts) > 1 else ""
                recent = list(history)
                ok_weighted = sum(1.0 if r.get("status") == "ok" else 0.5 if r.get("status") == "degraded" else 0.0 for r in recent)
                total = len(recent)
                availability_pct = round(100.0 * ok_weighted / total, 1) if total else 0.0
                latencies = [r["duration_ms"] for r in recent if r.get("duration_ms") is not None]
                avg_latency_ms = round(sum(latencies) / len(latencies), 0) if latencies else None
                last_failures = [r for r in reversed(recent) if r.get("status") == "error"][:CIRCUIT_OPEN_THRESHOLD]
                circuit_open = len(last_failures) >= CIRCUIT_OPEN_THRESHOLD and all(
                    r.get("status") == "error" for r in list(recent)[-CIRCUIT_OPEN_THRESHOLD:]
                )
                last_error = recent[-1].get("error") if recent and recent[-1].get("status") == "error" else None
                current_status = "down" if circuit_open else ("ok" if availability_pct >= 80 else "degraded")
                if source_name in overrides:
                    current_status = overrides[source_name]
                sources.append(
                    {
                        "source": source_name,
                        "agent": agent_name,
                        "availability_pct": availability_pct,
                        "avg_latency_ms": avg_latency_ms,
                        "status": current_status,
                        "circuit_open": circuit_open,
                        "last_error": last_error,
                        "last_results_count": len(recent),
                    }
                )
            degraded = sum(1 for s in sources if s["status"] == "degraded")
            down = sum(1 for s in sources if s["status"] == "down")
            return {
                "sources": sources,
                "summary": {
                    "total_sources": len(sources),
                    "degraded": degraded,
                    "down": down,
                    "ok": len(sources) - degraded - down,
                },
            }

    def clear(self) -> None:
        """Reset all source history. Call at the start of a new analysis run."""
        with self._lock:
            self._data.clear()

    def is_circuit_open(self, source_name: str, agent_name: str) -> bool:
        """True if this source/agent has failed CIRCUIT_OPEN_THRESHOLD times in a row."""
        key = self._key(source_name, agent_name)
        with self._lock:
            history = self._data.get(key)
            if not history or len(history) < CIRCUIT_OPEN_THRESHOLD:
                return False
            recent = list(history)[-CIRCUIT_OPEN_THRESHOLD:]
            return all(r.get("status") == "error" for r in recent)


_instance: Optional[HealthRegistry] = None
_instance_lock = threading.Lock()


def get_health_registry() -> Optional[HealthRegistry]:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HealthRegistry()
        return _instance
