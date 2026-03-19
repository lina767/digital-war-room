"""
State Service – analysis cache, agent status, escalation timeline, run history.

In-memory only. Single interface for all state; survives process lifetime but not restarts.
"""

import logging
import os
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUN_HISTORY_MAX = int(os.getenv("DWR_RUN_HISTORY_MAX", "50"))
ESCALATION_TIMELINE_MAX_POINTS = int(os.getenv("ESCALATION_TIMELINE_MAX_POINTS", "24"))


class StateService:
    """
    Single interface for analysis cache, last error, escalation timeline,
    agent status, and run history. In-memory backend.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_error: Dict[str, str] = {}
        self._timeline: Dict[str, List[Dict[str, Any]]] = {}
        self._agent_status: Dict[str, Dict[str, Any]] = {}
        self._run_history: deque = deque(maxlen=RUN_HISTORY_MAX)

    # --- Cache ---

    def get_cache(self, conflict: str) -> Optional[Dict[str, Any]]:
        """Return cached analysis entry or None. Entry is {result, at}."""
        return self._cache.get(conflict)

    def set_cache(self, conflict: str, result: Dict[str, Any], at: float) -> None:
        """Store analysis result."""
        self._cache[conflict] = {"result": result, "at": at}

    def get_cache_all(self) -> Dict[str, Dict[str, Any]]:
        """Return all cached entries."""
        return dict(self._cache)

    # --- Last error ---

    def get_last_error(self, conflict: str) -> Optional[str]:
        return self._last_error.get(conflict)

    def set_last_error(self, conflict: str, message: str) -> None:
        self._last_error[conflict] = message

    def pop_last_error(self, conflict: str) -> None:
        self._last_error.pop(conflict, None)

    def get_last_error_all(self) -> Dict[str, str]:
        return dict(self._last_error)

    # --- Escalation timeline ---

    def get_escalation_timeline(self, conflict: str) -> List[Dict[str, Any]]:
        return list(self._timeline.get(conflict) or [])

    def append_escalation_timeline(self, conflict: str, at: float, escalation_score: float) -> None:
        point = {"at": at, "escalation_score": round(escalation_score, 1)}
        if conflict not in self._timeline:
            self._timeline[conflict] = []
        self._timeline[conflict].append(point)
        self._timeline[conflict] = self._timeline[conflict][-ESCALATION_TIMELINE_MAX_POINTS:]

    def get_escalation_timeline_all(self) -> Dict[str, List[Dict[str, Any]]]:
        return {c: list(v) for c, v in self._timeline.items()}

    # --- Agent status ---

    def get_agent_status(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._agent_status)

    def set_agent_status(self, agent_key: str, status: Dict[str, Any]) -> None:
        self._agent_status[agent_key] = status

    def set_agent_status_full(self, status: Dict[str, Dict[str, Any]]) -> None:
        """Replace full agent status dict (built by routes from result)."""
        self._agent_status.clear()
        self._agent_status.update(status)

    # --- Run history ---

    def get_run_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        runs = list(self._run_history)[-limit:]
        runs.reverse()
        return runs

    def push_run_history_entry(self, entry: Dict[str, Any]) -> None:
        """Append one run summary (built by routes)."""
        self._run_history.append(entry)
