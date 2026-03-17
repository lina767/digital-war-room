"""
AgentStateStore – In-memory state persistence across analysis cycles.

Replaces the ad-hoc ``_previous_sigint`` / ``_previous_sigint_ts`` pattern
with a generic, typed store keyed by (conflict, agent_name).

Survives cycles but not server restarts (same semantics as the old pattern).
"""
import threading
from typing import Any, Dict, Optional, Tuple

from .base import CircuitBreakerState


class AgentStateStore:
    """Generic in-memory state store per (conflict, agent_name).

    Thread-safe via a global lock (contention is negligible at 4 cycles/day).
    """

    def __init__(self) -> None:
        self._results: Dict[Tuple[str, str], Tuple[Any, float]] = {}
        self._hashes: Dict[Tuple[str, str], str] = {}
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self._lock = threading.Lock()

    # -- Results (per conflict + agent) -------------------------------------

    def get_result(self, conflict: str, agent_name: str) -> Optional[Tuple[Any, float]]:
        """Return (last_result, timestamp) or None."""
        with self._lock:
            return self._results.get((conflict, agent_name))

    def set_result(self, conflict: str, agent_name: str, result: Any, timestamp: float) -> None:
        with self._lock:
            self._results[(conflict, agent_name)] = (result, timestamp)

    # -- Content hashes (for delta comparison) ------------------------------

    def get_content_hash(self, conflict: str, agent_name: str) -> Optional[str]:
        with self._lock:
            return self._hashes.get((conflict, agent_name))

    def set_content_hash(self, conflict: str, agent_name: str, content_hash: str) -> None:
        with self._lock:
            self._hashes[(conflict, agent_name)] = content_hash

    # -- Circuit breaker state (per agent, not per conflict) ----------------

    def get_circuit_breaker(self, agent_name: str) -> CircuitBreakerState:
        with self._lock:
            return self._circuit_breakers.get(agent_name, CircuitBreakerState())

    def set_circuit_breaker(self, agent_name: str, state: CircuitBreakerState) -> None:
        with self._lock:
            self._circuit_breakers[agent_name] = state

    # -- Utilities ----------------------------------------------------------

    def has_changed(self, conflict: str, agent_name: str, new_hash: str) -> bool:
        """True if the content hash differs from the last stored value."""
        old = self.get_content_hash(conflict, agent_name)
        if old is None:
            return True
        return old != new_hash

    def clear(self, conflict: Optional[str] = None) -> None:
        """Clear all state, or state for a specific conflict."""
        with self._lock:
            if conflict is None:
                self._results.clear()
                self._hashes.clear()
                self._circuit_breakers.clear()
            else:
                keys_to_remove = [k for k in self._results if k[0] == conflict]
                for k in keys_to_remove:
                    del self._results[k]
                hash_keys = [k for k in self._hashes if k[0] == conflict]
                for k in hash_keys:
                    del self._hashes[k]


# Module-level singleton
_global_store: Optional[AgentStateStore] = None


def get_agent_state_store() -> AgentStateStore:
    """Return the global AgentStateStore singleton (created on first call)."""
    global _global_store
    if _global_store is None:
        _global_store = AgentStateStore()
    return _global_store
