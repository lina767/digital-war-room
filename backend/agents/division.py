"""
DivisionHead – Base class for organizational groupings of agents.

Division summaries are pure functions of agent results: weighted score,
anomaly detection, rule-based summary. No I/O, no LLM in the default path.
Optional Haiku can be enabled via USE_DIVISION_HAIKU for division-level briefings.
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from .dag_scheduler import DAGNode, ResultStore

logger = logging.getLogger(__name__)

# When False (default), division summary is pure: scores + anomalies + rule-based text only.
USE_DIVISION_HAIKU = os.getenv("USE_DIVISION_HAIKU", "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DivisionAnomaly(BaseModel):
    """Anomaly detected within a division's agents."""

    type: str  # "contradiction" | "score_outlier" | "threshold_breach" | "missing_agent"
    description: str
    severity: str = "medium"  # "low" | "medium" | "high"
    agents_involved: List[str] = Field(default_factory=list)


class DivisionResult(BaseModel):
    """Output of a division summary node (Tier 4)."""

    division: str
    score: float = 0.0
    agent_scores: Dict[str, float] = Field(default_factory=dict)
    anomalies: List[DivisionAnomaly] = Field(default_factory=list)
    summary: str = ""
    haiku_used: bool = False
    agents_ok: List[str] = Field(default_factory=list)
    agents_failed: List[str] = Field(default_factory=list)
    duration_ms: int = 0


class CycleLog(BaseModel):
    """Structured log entry emitted at end of each cycle."""

    cycle_id: str = ""
    conflict: str = ""
    timestamp: str = ""
    total_duration_ms: int = 0
    dag_nodes_total: int = 0
    dag_nodes_failed: int = 0
    divisions: Dict[str, Any] = Field(default_factory=dict)
    composite_score: float = 0.0
    composite_score_delta: Optional[float] = None
    threat_level: str = ""
    entity_count: int = 0


# ---------------------------------------------------------------------------
# DivisionHead base
# ---------------------------------------------------------------------------


class DivisionHead(ABC):
    """Abstract base for all five divisions.

    Subclasses define their agents, enrichment nodes, weights, and
    anomaly-detection rules.
    """

    name: str = ""
    agent_names: List[str] = []
    enrichment_nodes: List[str] = []
    weight_map: Dict[str, float] = {}
    min_required_analysts: int = 1

    # Haiku trigger config
    anomaly_score_spread: float = 50.0
    anomaly_threshold_score: float = 75.0
    haiku_periodic_cycles: int = 0  # 0 = off
    _cycle_count: int = 0

    def __init__(self) -> None:
        self._cycle_count = 0

    # -- DAG registration ---------------------------------------------------

    def get_dag_nodes(self) -> List[DAGNode]:
        """Return all DAG nodes this division owns (agents + enrichment + summary)."""
        nodes = []
        for agent_name in self.agent_names:
            nodes.append(
                DAGNode(
                    id=agent_name,
                    node_type="agent",
                    owner_division=self.name,
                    streamable=True,
                    timeout_s=75.0,
                )
            )
        nodes.extend(self._get_enrichment_nodes())
        nodes.append(self._get_summary_node())
        return nodes

    @abstractmethod
    def _get_enrichment_nodes(self) -> List[DAGNode]:
        """Return enrichment DAG nodes owned by this division."""
        ...

    def _get_summary_node(self) -> DAGNode:
        """Return the Tier 4 summary node for this division."""
        deps = list(self.enrichment_nodes) if self.enrichment_nodes else list(self.agent_names)
        remaining_agents = [a for a in self.agent_names if a not in deps]
        deps.extend(remaining_agents)
        return DAGNode(
            id=f"{self.name}_summary",
            dependencies=deps,
            node_type="division_summary",
            owner_division=self.name,
            streamable=True,
            timeout_s=10.0,
        )

    # -- Executors for DAG --------------------------------------------------

    def get_executors(self) -> Dict[str, Callable]:
        """Return executor callables for this division's enrichment + summary nodes."""
        executors = self._get_enrichment_executors()
        executors[f"{self.name}_summary"] = self._execute_summary
        return executors

    @abstractmethod
    def _get_enrichment_executors(self) -> Dict[str, Callable]:
        """Return enrichment executor callables keyed by node_id."""
        ...

    # -- Summary computation (Tier 4 node) ----------------------------------

    def _execute_summary(self, store: ResultStore) -> DivisionResult:
        """Compute division summary: scores, anomalies, optional Haiku."""
        start = time.perf_counter()
        self._cycle_count += 1

        agent_scores: Dict[str, float] = {}
        agents_ok: List[str] = []
        agents_failed: List[str] = []

        for agent_name in self.agent_names:
            result = store.get(agent_name)
            if result is None:
                agents_failed.append(agent_name)
                continue
            score = self._extract_score(agent_name, result)
            if score is not None:
                agent_scores[agent_name] = score
                agents_ok.append(agent_name)
            else:
                agents_failed.append(agent_name)

        # Weighted score with normalization for missing agents
        division_score = self._compute_weighted_score(agent_scores)

        # Anomaly detection
        anomalies = self._detect_anomalies(agent_scores, agents_failed)

        # Summary text (rule-based; Haiku on trigger)
        summary = self._build_summary(agent_scores, anomalies, store)

        haiku_used = False
        if self._should_trigger_haiku(anomalies):
            haiku_summary = self._call_haiku(agent_scores, anomalies, store)
            if haiku_summary:
                summary = haiku_summary
                haiku_used = True

        duration_ms = int((time.perf_counter() - start) * 1000)

        return DivisionResult(
            division=self.name,
            score=round(division_score, 1),
            agent_scores=agent_scores,
            anomalies=anomalies,
            summary=summary,
            haiku_used=haiku_used,
            agents_ok=agents_ok,
            agents_failed=agents_failed,
            duration_ms=duration_ms,
        )

    def _extract_score(self, agent_name: str, result: Any) -> Optional[float]:
        """Extract the numeric score from an agent result (dict or BaseModel)."""
        score_fields = {
            "finint": "escalation_score",
        }
        field = score_fields.get(agent_name, f"{agent_name}_score")

        if isinstance(result, dict):
            val = result.get(field, result.get("score"))
        elif hasattr(result, field):
            val = getattr(result, field)
        elif hasattr(result, "score"):
            val = result.score
        elif hasattr(result, "data"):
            data = result.data
            if isinstance(data, dict):
                val = data.get(field, data.get("score"))
            elif hasattr(data, field):
                val = getattr(data, field)
            else:
                val = None
        else:
            val = None

        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _compute_weighted_score(self, agent_scores: Dict[str, float]) -> float:
        """Weighted average with normalization for missing agents."""
        if not agent_scores:
            return 0.0
        total_weight = sum(self.weight_map.get(name, 0.0) for name in agent_scores)
        if total_weight <= 0:
            return sum(agent_scores.values()) / len(agent_scores)
        return sum(score * (self.weight_map.get(name, 0.0) / total_weight) for name, score in agent_scores.items())

    def _detect_anomalies(self, agent_scores: Dict[str, float], agents_failed: List[str]) -> List[DivisionAnomaly]:
        """Base anomaly detection: contradiction, threshold, missing agents."""
        anomalies: List[DivisionAnomaly] = []

        if agents_failed:
            anomalies.append(
                DivisionAnomaly(
                    type="missing_agent",
                    description=f"Agents unavailable: {', '.join(agents_failed)}",
                    severity="medium",
                    agents_involved=agents_failed,
                )
            )

        scores = list(agent_scores.values())
        if len(scores) >= 2:
            spread = max(scores) - min(scores)
            if spread > self.anomaly_score_spread:
                high = max(agent_scores, key=agent_scores.get)
                low = min(agent_scores, key=agent_scores.get)
                anomalies.append(
                    DivisionAnomaly(
                        type="contradiction",
                        description=f"Score spread {spread:.0f}: {high}={agent_scores[high]:.0f} vs {low}={agent_scores[low]:.0f}",
                        severity="high",
                        agents_involved=[high, low],
                    )
                )

        for name, score in agent_scores.items():
            if score > self.anomaly_threshold_score:
                anomalies.append(
                    DivisionAnomaly(
                        type="threshold_breach",
                        description=f"{name} score {score:.0f} > threshold {self.anomaly_threshold_score:.0f}",
                        severity="high",
                        agents_involved=[name],
                    )
                )

        return anomalies

    def _build_summary(
        self, agent_scores: Dict[str, float], anomalies: List[DivisionAnomaly], store: ResultStore
    ) -> str:
        """Rule-based summary text. Override for domain-specific logic."""
        parts = [f"{self.name.title()} Division:"]
        for name, score in sorted(agent_scores.items(), key=lambda x: -x[1]):
            parts.append(f"  {name}: {score:.0f}")
        if anomalies:
            parts.append(f"  Anomalies: {len(anomalies)}")
            for a in anomalies:
                parts.append(f"    [{a.severity}] {a.description}")
        return "\n".join(parts)

    def _should_trigger_haiku(self, anomalies: List[DivisionAnomaly]) -> bool:
        """Decide whether to make a Haiku LLM call. Disabled by default (pure division summary)."""
        if not USE_DIVISION_HAIKU:
            return False
        has_high_severity = any(a.severity == "high" for a in anomalies)
        periodic = self.haiku_periodic_cycles > 0 and self._cycle_count % self.haiku_periodic_cycles == 0
        return has_high_severity or periodic

    def _call_haiku(
        self, agent_scores: Dict[str, float], anomalies: List[DivisionAnomaly], store: ResultStore
    ) -> Optional[str]:
        """Override to make an actual Haiku LLM call. Base returns None."""
        return None
