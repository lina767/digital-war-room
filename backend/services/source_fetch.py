"""
Shared source fetch – per-run cache to deduplicate external API calls across agents.

Agents that need the same data (e.g. ACLED, OFAC list) can call get(conflict, source_id, fetcher)
and receive a cached result for the duration of the run. Cleared at the start of each
analyze_conflict_dag run so each run gets fresh data without duplicate HTTP calls within the run.
"""

import hashlib
import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_run_cache: dict = {}
_lock = threading.Lock()


def _cache_key(conflict: str, source_id: str, params: Optional[dict] = None) -> str:
    if params is None:
        params = {}
    raw = f"{conflict}:{source_id}:{sorted(params.items())}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get(
    conflict: str,
    source_id: str,
    fetcher: Callable[[], Any],
    params: Optional[dict] = None,
) -> Any:
    """Return cached value for (conflict, source_id, params) or call fetcher() and cache."""
    key = _cache_key(conflict, source_id, params)
    with _lock:
        if key in _run_cache:
            return _run_cache[key]
    try:
        value = fetcher()
    except Exception as e:
        logger.warning("[source_fetch] %s failed: %s", source_id, e)
        raise
    with _lock:
        _run_cache[key] = value
    return value


def clear_run_cache() -> None:
    """Clear the per-run cache. Call at the start of each DAG run."""
    with _lock:
        _run_cache.clear()
