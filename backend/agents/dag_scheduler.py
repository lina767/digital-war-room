"""
DAG-Scheduler – Dependency-driven execution via graphlib.TopologicalSorter.

Each agent, enrichment step, division summary, and the CEO synthesis is a DAGNode.
Nodes start as soon as their hard dependencies are satisfied. Optional (soft)
dependencies deliver None when unavailable; the node decides how to handle that.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from graphlib import TopologicalSorter
from typing import Any, Callable, Dict, Generator, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DAGNode
# ---------------------------------------------------------------------------


class DAGNode(BaseModel):
    """Single node in the execution DAG."""

    id: str
    dependencies: List[str] = Field(default_factory=list)
    optional_deps: List[str] = Field(default_factory=list)
    owner_division: Optional[str] = None
    node_type: str = "agent"  # "agent" | "enrichment" | "division_summary" | "synthesis"
    fallback: Optional[Any] = None
    timeout_s: float = 75.0
    streamable: bool = False


# ---------------------------------------------------------------------------
# ResultStore
# ---------------------------------------------------------------------------


class ResultStore:
    """Thread-safe store for DAG node results within a single analysis run."""

    def __init__(self, cycle_id: str = "", conflict: str = ""):
        self.cycle_id = cycle_id
        self.conflict = conflict
        self.created_at: float = time.time()
        self._results: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def set(self, node_id: str, result: Any) -> None:
        with self._lock:
            self._results[node_id] = result

    def get(self, node_id: str) -> Optional[Any]:
        with self._lock:
            return self._results.get(node_id)

    def get_many(self, node_ids: List[str]) -> Dict[str, Any]:
        with self._lock:
            return {nid: self._results.get(nid) for nid in node_ids}

    def has(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._results

    def all_results(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._results)

    def __contains__(self, node_id: str) -> bool:
        return self.has(node_id)


class ResultStoreManager:
    """Manages ResultStore lifecycle: creation, finishing, cleanup."""

    def __init__(self, retention_cycles: int = 5, retention_minutes: float = 60.0):
        self._stores: List[ResultStore] = []
        self._retention_cycles = retention_cycles
        self._retention_minutes = retention_minutes
        self._lock = threading.Lock()

    def create_store(self, conflict: str, cycle_id: str) -> ResultStore:
        store = ResultStore(cycle_id=cycle_id, conflict=conflict)
        with self._lock:
            self._stores.append(store)
        return store

    def finish_cycle(self, store: ResultStore) -> None:
        """Hook for CycleLog writing and CycleArchive persistence."""
        pass

    def cleanup(self) -> None:
        """Remove stores older than retention limits."""
        now = time.time()
        cutoff = now - (self._retention_minutes * 60)
        with self._lock:
            if len(self._stores) > self._retention_cycles:
                keep = self._stores[-self._retention_cycles :]
            else:
                keep = list(self._stores)
            self._stores = [s for s in keep if s.created_at >= cutoff]


# ---------------------------------------------------------------------------
# DAGScheduler
# ---------------------------------------------------------------------------


class DAGScheduler:
    """Dependency-driven scheduler using graphlib.TopologicalSorter.

    Nodes without outstanding dependencies execute in parallel.
    Each node writes its result into the ResultStore.
    """

    def __init__(self, nodes: List[DAGNode], max_workers: int = 14):
        self._nodes: Dict[str, DAGNode] = {n.id: n for n in nodes}
        self._max_workers = max_workers
        self._validate()

    def _validate(self) -> None:
        """Check all dependencies reference known nodes."""
        known = set(self._nodes.keys())
        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep not in known:
                    raise ValueError(f"DAGNode '{node.id}' has unknown hard dep '{dep}'")
            for dep in node.optional_deps:
                if dep not in known:
                    raise ValueError(f"DAGNode '{node.id}' has unknown optional dep '{dep}'")

    def run(self, executors: Dict[str, Callable], store: ResultStore) -> ResultStore:
        """Execute all nodes in topological order.

        Args:
            executors: mapping of node_id -> callable(store) -> result
            store: ResultStore to read deps from and write results into
        """
        dep_graph = {nid: set(n.dependencies) for nid, n in self._nodes.items()}
        sorter = TopologicalSorter(dep_graph)
        sorter.prepare()

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            while sorter.is_active():
                ready = sorter.get_ready()
                futures = {}
                for nid in ready:
                    node = self._nodes[nid]
                    executor = executors.get(nid)
                    if executor is None:
                        logger.warning("No executor for node '%s' – skipping", nid)
                        store.set(nid, node.fallback)
                        sorter.done(nid)
                        continue
                    futures[pool.submit(self._run_node, node, executor, store)] = nid

                for future in futures:
                    nid = futures[future]
                    try:
                        result = future.result(timeout=self._nodes[nid].timeout_s)
                        store.set(nid, result)
                    except FuturesTimeoutError:
                        logger.warning("Node '%s' timed out (%.0fs)", nid, self._nodes[nid].timeout_s)
                        store.set(nid, self._nodes[nid].fallback)
                    except Exception as exc:
                        logger.warning("Node '%s' failed: %s", nid, exc)
                        store.set(nid, self._nodes[nid].fallback)
                    sorter.done(nid)

        return store

    def run_streaming(self, executors: Dict[str, Callable], store: ResultStore) -> Generator:
        """Like run(), but yields (node_id, result) only for streamable nodes.

        Frontend receives only Tier-1 (Agent-Results) and Tier-4 (Division-Summaries),
        not intermediate enrichment steps.
        """
        dep_graph = {nid: set(n.dependencies) for nid, n in self._nodes.items()}
        sorter = TopologicalSorter(dep_graph)
        sorter.prepare()

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            while sorter.is_active():
                ready = sorter.get_ready()
                futures = {}
                for nid in ready:
                    node = self._nodes[nid]
                    executor = executors.get(nid)
                    if executor is None:
                        store.set(nid, node.fallback)
                        sorter.done(nid)
                        if node.streamable:
                            yield (nid, node.fallback)
                        continue
                    futures[pool.submit(self._run_node, node, executor, store)] = nid

                for future in futures:
                    nid = futures[future]
                    node = self._nodes[nid]
                    try:
                        result = future.result(timeout=node.timeout_s)
                    except (FuturesTimeoutError, Exception) as exc:
                        logger.warning("Node '%s' failed/timed out: %s", nid, exc)
                        result = node.fallback
                    store.set(nid, result)
                    sorter.done(nid)
                    if node.streamable:
                        yield (nid, result)

    @staticmethod
    def _run_node(node: DAGNode, executor: Callable, store: ResultStore) -> Any:
        """Execute a single node's callable, passing the store for dep lookup."""
        try:
            from observability import run_node_traced

            conflict = getattr(store, "conflict", "") or ""
            return run_node_traced(node.id, node.node_type, conflict, lambda: executor(store))
        except Exception:
            return executor(store)
