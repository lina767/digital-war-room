"""
State Service – analysis cache, agent status, escalation timeline, run history.

In-memory only. Keys are scoped by tenant_id + conflict (multi-tenancy).
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUN_HISTORY_MAX = int(os.getenv("DWR_RUN_HISTORY_MAX", "50"))
ESCALATION_TIMELINE_MAX_POINTS = int(os.getenv("ESCALATION_TIMELINE_MAX_POINTS", "24"))


def _tid(tenant_id: Optional[uuid.UUID]) -> str:
    if tenant_id is not None:
        return str(tenant_id)
    try:
        from services.request_context import get_current_tenant_id

        return str(get_current_tenant_id())
    except Exception:
        from services.tenant_constants import get_default_tenant_id

        return str(get_default_tenant_id())


def _scope_key(tenant_id: Optional[uuid.UUID], conflict: str) -> str:
    return f"{_tid(tenant_id)}\n{conflict}"


class StateService:
    """
    Single interface for analysis cache, last error, escalation timeline,
    agent status, and run history. In-memory backend; tenant-scoped keys.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_error: Dict[str, str] = {}
        self._timeline: Dict[str, List[Dict[str, Any]]] = {}
        self._agent_status: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._run_history: deque = deque(maxlen=RUN_HISTORY_MAX)

    # --- Cache ---

    def get_cache(self, conflict: str, tenant_id: Optional[uuid.UUID] = None) -> Optional[Dict[str, Any]]:
        """Return cached analysis entry or None. Entry is {result, at}."""
        return self._cache.get(_scope_key(tenant_id, conflict))

    def set_cache(self, conflict: str, result: Dict[str, Any], at: float, tenant_id: Optional[uuid.UUID] = None) -> None:
        """Store analysis result."""
        self._cache[_scope_key(tenant_id, conflict)] = {"result": result, "at": at}

    def get_cache_all(self, tenant_id: Optional[uuid.UUID] = None) -> Dict[str, Dict[str, Any]]:
        """Return cached entries for one tenant (conflict -> entry)."""
        prefix = _tid(tenant_id) + "\n"
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in self._cache.items():
            if k.startswith(prefix):
                conflict = k[len(prefix) :]
                out[conflict] = v
        return out

    # --- Last error ---

    def get_last_error(self, conflict: str, tenant_id: Optional[uuid.UUID] = None) -> Optional[str]:
        return self._last_error.get(_scope_key(tenant_id, conflict))

    def set_last_error(self, conflict: str, message: str, tenant_id: Optional[uuid.UUID] = None) -> None:
        self._last_error[_scope_key(tenant_id, conflict)] = message

    def pop_last_error(self, conflict: str, tenant_id: Optional[uuid.UUID] = None) -> None:
        self._last_error.pop(_scope_key(tenant_id, conflict), None)

    def get_last_error_all(self, tenant_id: Optional[uuid.UUID] = None) -> Dict[str, str]:
        prefix = _tid(tenant_id) + "\n"
        return {k[len(prefix) :]: v for k, v in self._last_error.items() if k.startswith(prefix)}

    # --- Escalation timeline ---

    def get_escalation_timeline(self, conflict: str, tenant_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        return list(self._timeline.get(_scope_key(tenant_id, conflict)) or [])

    def append_escalation_timeline(
        self, conflict: str, at: float, escalation_score: float, tenant_id: Optional[uuid.UUID] = None
    ) -> None:
        sk = _scope_key(tenant_id, conflict)
        point = {"at": at, "escalation_score": round(escalation_score, 1)}
        if sk not in self._timeline:
            self._timeline[sk] = []
        self._timeline[sk].append(point)
        self._timeline[sk] = self._timeline[sk][-ESCALATION_TIMELINE_MAX_POINTS:]

    def get_escalation_timeline_all(self, tenant_id: Optional[uuid.UUID] = None) -> Dict[str, List[Dict[str, Any]]]:
        prefix = _tid(tenant_id) + "\n"
        out: Dict[str, List[Dict[str, Any]]] = {}
        for k, v in self._timeline.items():
            if k.startswith(prefix):
                out[k[len(prefix) :]] = list(v)
        return out

    # --- Agent status ---

    def get_agent_status(self, tenant_id: Optional[uuid.UUID] = None) -> Dict[str, Dict[str, Any]]:
        tid = _tid(tenant_id)
        return dict(self._agent_status.get(tid) or {})

    def set_agent_status(self, agent_key: str, status: Dict[str, Any], tenant_id: Optional[uuid.UUID] = None) -> None:
        tid = _tid(tenant_id)
        if tid not in self._agent_status:
            self._agent_status[tid] = {}
        self._agent_status[tid][agent_key] = status

    def set_agent_status_full(self, status: Dict[str, Dict[str, Any]], tenant_id: Optional[uuid.UUID] = None) -> None:
        tid = _tid(tenant_id)
        self._agent_status[tid] = dict(status)

    # --- Run history ---

    def get_run_history(self, limit: int = 20, tenant_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        want = str(_tid(tenant_id))
        runs = [r for r in self._run_history if str(r.get("tenant_id")) == want]
        runs = runs[-limit:]
        runs.reverse()
        return runs

    def push_run_history_entry(self, entry: Dict[str, Any], tenant_id: Optional[uuid.UUID] = None) -> None:
        """Append one run summary (built by routes)."""
        e = dict(entry)
        e["tenant_id"] = str(_tid(tenant_id))
        self._run_history.append(e)
