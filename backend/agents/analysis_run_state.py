"""
Zentraler Lesezugriff auf den aktiven Analysis-Run (ResultStore) aus beliebigem Agent-Code.

Während ein DAG-Knoten läuft, bindet der Scheduler den gemeinsamen ResultStore
thread-lokal. Agent-Module können so Ergebnisse anderer Knoten (z. B. ``sigint``,
``news``) lesen, sobald diese im Store liegen — ohne Umweg über die CEO-/Supervisor-Synthese.

Außerhalb eines laufenden Knotens liefern die Hilfsfunktionen None bzw. leere Dicts.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Protocol


class AnalysisRunReader(Protocol):
    """Minimal interface of ResultStore for peer reads (avoids circular imports)."""

    cycle_id: str
    conflict: str

    def get(self, node_id: str) -> Optional[Any]: ...

    def get_many(self, node_ids: List[str]) -> Dict[str, Any]: ...


_tls = threading.local()


def _reader() -> Optional[AnalysisRunReader]:
    return getattr(_tls, "reader", None)


def get_current_analysis_run() -> Optional[AnalysisRunReader]:
    """Aktiver ResultStore dieser Ausführung, oder None wenn nicht in einem DAG-Knoten."""
    return _reader()


def get_current_conflict() -> str:
    r = _reader()
    return (r.conflict or "") if r else ""


def get_current_cycle_id() -> str:
    r = _reader()
    return (r.cycle_id or "") if r else ""


def get_peer_result(node_id: str) -> Optional[Any]:
    """Ergebnis eines anderen DAG-Knotens (Agent-ID), falls bereits im Store."""
    r = _reader()
    return r.get(node_id) if r else None


def get_peer_results(node_ids: List[str]) -> Dict[str, Any]:
    """Mehrere Knoten auf einmal; fehlende Keys haben Wert None (wie ResultStore.get_many)."""
    r = _reader()
    if not r:
        return {nid: None for nid in node_ids}
    return r.get_many(node_ids)


def get_peers_snapshot(*, exclude: Optional[str] = None) -> Dict[str, Any]:
    """Alle Registry-Agenten mit bereits vorliegendem Ergebnis im aktuellen Run (ohne ``exclude``).

    Nur Keys mit nicht-``None``-Werten — kompakt für Prompts/Weiterverarbeitung.
    """
    from .registry import get_agent_registry

    out: Dict[str, Any] = {}
    for desc in get_agent_registry().all_agents():
        if exclude and desc.name == exclude:
            continue
        val = get_peer_result(desc.name)
        if val is not None:
            out[desc.name] = val
    return out


def invoke_with_current_store(
    store: AnalysisRunReader,
    executor: Callable[[AnalysisRunReader], Any],
) -> Any:
    """Intern: Store für die Dauer von ``executor(store)`` thread-lokal setzen."""
    prev = getattr(_tls, "reader", None)
    _tls.reader = store
    try:
        return executor(store)
    finally:
        _tls.reader = prev
