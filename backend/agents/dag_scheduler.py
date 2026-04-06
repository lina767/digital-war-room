"""
DAG-Scheduler – Dependency-driven execution via graphlib.TopologicalSorter.

Each agent, enrichment step, division summary, and the CEO synthesis is a DAGNode.
Nodes start as soon as their hard dependencies are satisfied. Optional (soft)
dependencies deliver None when unavailable; the node decides how to handle that.
"""

import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from graphlib import TopologicalSorter
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

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

    def _build_sorter(self) -> TopologicalSorter:
        # Include optional_deps in graph so execution order is deterministic; node still gets None if dep missing.
        dep_graph = {nid: set(n.dependencies) | set(n.optional_deps) for nid, n in self._nodes.items()}
        sorter = TopologicalSorter(dep_graph)
        sorter.prepare()
        return sorter

    def _run_internal(
        self, executors: Dict[str, Callable], store: ResultStore, *, stream_results: bool
    ) -> Generator[Tuple[str, Any], None, None]:
        sorter = self._build_sorter()
        pool = ThreadPoolExecutor(max_workers=self._max_workers)
        in_flight: Dict[Future, Tuple[str, float]] = {}
        fallback_events = {"missing_executor": 0, "exec_failed": 0, "timed_out": 0}
        try:
            while sorter.is_active() or in_flight:
                ready = sorter.get_ready() if sorter.is_active() else ()
                for nid in ready:
                    node = self._nodes[nid]
                    executor = executors.get(nid)
                    if executor is None:
                        logger.warning("No executor for node '%s' – skipping", nid)
                        store.set(nid, node.fallback)
                        fallback_events["missing_executor"] += 1
                        sorter.done(nid)
                        if stream_results and node.streamable:
                            yield (nid, node.fallback)
                        continue
                    t_submit = time.perf_counter()
                    in_flight[pool.submit(self._run_node, node, executor, store)] = (nid, t_submit)

                if not in_flight:
                    continue

                done, _ = wait(in_flight.keys(), timeout=0.05, return_when=FIRST_COMPLETED)
                now = time.perf_counter()

                # Process completed futures immediately so downstream nodes can start ASAP.
                for future in done:
                    nid, t_submit = in_flight.pop(future)
                    node = self._nodes[nid]
                    try:
                        result, duration_ms = future.result()
                        timed_out = False
                        exec_failed = False
                    except Exception as exc:
                        logger.warning("Node '%s' failed: %s", nid, exc)
                        result = node.fallback
                        duration_ms = (now - t_submit) * 1000
                        timed_out = False
                        exec_failed = True
                        fallback_events["exec_failed"] += 1

                    store.set(nid, result)
                    self._emit_agent_heartbeat(
                        nid,
                        node,
                        store,
                        result,
                        duration_ms,
                        timed_out=timed_out,
                        exec_failed=exec_failed,
                    )
                    sorter.done(nid)
                    if stream_results and node.streamable:
                        yield (nid, result)

                # Independent timeout handling avoids head-of-line blocking on slow tasks.
                timed_out_futures: List[Future] = []
                for future, (nid, t_submit) in in_flight.items():
                    node = self._nodes[nid]
                    if (now - t_submit) >= node.timeout_s:
                        timed_out_futures.append(future)
                for future in timed_out_futures:
                    nid, t_submit = in_flight.pop(future)
                    node = self._nodes[nid]
                    logger.warning("Node '%s' timed out (%.0fs)", nid, node.timeout_s)
                    future.cancel()
                    result = node.fallback
                    duration_ms = (now - t_submit) * 1000
                    store.set(nid, result)
                    fallback_events["timed_out"] += 1
                    self._emit_agent_heartbeat(
                        nid,
                        node,
                        store,
                        result,
                        duration_ms,
                        timed_out=True,
                        exec_failed=False,
                    )
                    sorter.done(nid)
                    if stream_results and node.streamable:
                        yield (nid, result)
        finally:
            if any(v > 0 for v in fallback_events.values()):
                suffix = " (streaming)" if stream_results else ""
                logger.warning("DAG fallback summary%s: %s", suffix, fallback_events)
            # Do not block the whole analysis run on stuck worker threads after timeout fallback.
            pool.shutdown(wait=False, cancel_futures=True)

    def run(self, executors: Dict[str, Callable], store: ResultStore) -> ResultStore:
        """Execute all nodes in topological order.

        Args:
            executors: mapping of node_id -> callable(store) -> result
            store: ResultStore to read deps from and write results into
        """
        for _ in self._run_internal(executors, store, stream_results=False):
            pass
        return store

    @staticmethod
    def _emit_agent_heartbeat(
        nid: str,
        node: DAGNode,
        store: ResultStore,
        result: Any,
        duration_ms: float,
        *,
        timed_out: bool,
        exec_failed: bool,
    ) -> None:
        try:
            from .heartbeat_hooks import classify_agent_outcome, sources_for_agent_snapshot
            from .registry import get_agent_registry
            from services.agent_heartbeat_store import record_agent_heartbeat

            if get_agent_registry().get(nid) is None:
                return
            outcome = classify_agent_outcome(result, timed_out=timed_out, exec_failed=exec_failed)
            ratio, srcs = sources_for_agent_snapshot(nid)
            record_agent_heartbeat(
                agent=nid,
                conflict=getattr(store, "conflict", "") or "",
                cycle_id=getattr(store, "cycle_id", "") or "",
                outcome=outcome,
                duration_ms=duration_ms,
                sources_ok_ratio=ratio,
                sources=srcs,
            )
        except Exception as exc:
            logger.debug("agent heartbeat not recorded for %s: %s", nid, exc)

    def run_streaming(self, executors: Dict[str, Callable], store: ResultStore) -> Generator:
        """Like run(), but yields (node_id, result) only for streamable nodes.

        Frontend receives only Tier-1 (Agent-Results) and Tier-4 (Division-Summaries),
        not intermediate enrichment steps.
        """
        yield from self._run_internal(executors, store, stream_results=True)

    @staticmethod
    def _run_node(node: DAGNode, executor: Callable, store: ResultStore) -> Tuple[Any, float]:
        """Execute a single node's callable, passing the store for dep lookup. Returns (result, duration_ms)."""
        from .analysis_run_state import invoke_with_current_store

        t0 = time.perf_counter()

        def _run() -> Any:
            return invoke_with_current_store(store, executor)

        try:
            from observability import run_node_traced

            conflict = getattr(store, "conflict", "") or ""
            out = run_node_traced(node.id, node.node_type, conflict, _run)
        except Exception:
            out = _run()
        duration_ms = (time.perf_counter() - t0) * 1000
        return out, duration_ms
