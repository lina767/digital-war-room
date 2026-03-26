"""
AgentRegistry – Plugin architecture for agent discovery and registration.

New agents implement BaseAgent, add an AgentDescriptor to the registry
(via config or self-registration), and the DivisionHead auto-discovers them.
No code changes in supervisor or division heads required.
"""

import importlib
import logging
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentDescriptor(BaseModel):
    """Declarative agent metadata for registry-based discovery."""

    name: str
    module: str  # e.g. "agents.energy_agent"
    entry_func: str  # e.g. "run_energy_agent"
    division: str  # e.g. "financial"
    score_field: str  # e.g. "energy_score"
    weight: float = 0.0  # within-division weight (set by config)
    enabled: bool = True


# Default agent descriptors matching the existing agents (see docs/AGENTS.md)
DEFAULT_AGENTS: List[AgentDescriptor] = [
    AgentDescriptor(
        name="sigint",
        module="agents.sigint_agent",
        entry_func="run_sigint_agent",
        division="military",
        score_field="sigint_score",
    ),
    AgentDescriptor(
        name="geoint",
        module="agents.geoint_agent",
        entry_func="run_geoint_agent",
        division="military",
        score_field="geoint_score",
    ),
    AgentDescriptor(
        name="satintel",
        module="agents.satintel_agent",
        entry_func="run_satintel_agent",
        division="military",
        score_field="satintel_score",
    ),
    AgentDescriptor(
        name="proximity",
        module="agents.proximity_agent",
        entry_func="run_proximity_agent",
        division="military",
        score_field="proximity_score",
    ),
    AgentDescriptor(
        name="chokepoint",
        module="agents.chokepoint_agent",
        entry_func="run_chokepoint_agent",
        division="military",
        score_field="chokepoint_score",
    ),
    AgentDescriptor(
        name="finint",
        module="agents.finint_agent",
        entry_func="run_finint_agent",
        division="financial",
        score_field="escalation_score",
    ),
    AgentDescriptor(
        name="energy",
        module="agents.energy_agent",
        entry_func="run_energy_agent",
        division="financial",
        score_field="energy_score",
    ),
    AgentDescriptor(
        name="news",
        module="agents.news_agent",
        entry_func="run_news_agent",
        division="information",
        score_field="news_score",
    ),
    AgentDescriptor(
        name="socmint",
        module="agents.socmint_agent",
        entry_func="run_socmint_agent",
        division="information",
        score_field="socmint_score",
    ),
    AgentDescriptor(
        name="mediaint",
        module="agents.mediaint_agent",
        entry_func="run_mediaint_agent",
        division="information",
        score_field="mediaint_score",
    ),
    AgentDescriptor(
        name="narrative",
        module="agents.signal_framework_agent",
        entry_func="run_signal_framework_agent",
        division="information",
        score_field="narrative_score",
    ),
    AgentDescriptor(
        name="diplo",
        module="agents.diplo_agent",
        entry_func="run_diplo_agent",
        division="political",
        score_field="diplo_score",
    ),
    AgentDescriptor(
        name="protest",
        module="agents.protest_agent",
        entry_func="run_protest_agent",
        division="political",
        score_field="protest_score",
    ),
    AgentDescriptor(
        name="techint",
        module="agents.techint_agent",
        entry_func="run_techint_agent",
        division="technical",
        score_field="techint_score",
    ),
    AgentDescriptor(
        name="cyber",
        module="agents.cyber_agent",
        entry_func="run_cyber_agent",
        division="technical",
        score_field="cyber_score",
    ),
    AgentDescriptor(
        name="pentagon",
        module="agents.pentagon_agent",
        entry_func="run_pentagon_agent",
        division="military",
        score_field="pentagon_score",
    ),
]


class AgentRegistry:
    """Central registry for all agent descriptors.

    Supports lazy instantiation: agents are imported only when first needed.
    """

    def __init__(self, agents: Optional[List[AgentDescriptor]] = None):
        descriptors = agents if agents is not None else DEFAULT_AGENTS
        self._agents: Dict[str, AgentDescriptor] = {a.name: a for a in descriptors}
        self._entry_funcs: Dict[str, Callable] = {}

    def register(self, descriptor: AgentDescriptor) -> None:
        """Register a new agent (or replace an existing one)."""
        self._agents[descriptor.name] = descriptor
        self._entry_funcs.pop(descriptor.name, None)

    def get(self, name: str) -> Optional[AgentDescriptor]:
        return self._agents.get(name)

    def get_by_division(self, division: str) -> List[AgentDescriptor]:
        return [a for a in self._agents.values() if a.division == division and a.enabled]

    def all_agents(self) -> List[AgentDescriptor]:
        return [a for a in self._agents.values() if a.enabled]

    def get_entry_func(self, name: str) -> Optional[Callable]:
        """Lazy-import and return the entry function for an agent."""
        if name in self._entry_funcs:
            return self._entry_funcs[name]
        desc = self._agents.get(name)
        if desc is None:
            return None
        try:
            module = importlib.import_module(desc.module)
            func = getattr(module, desc.entry_func)
            self._entry_funcs[name] = func
            return func
        except (ImportError, AttributeError) as e:
            logger.error("Failed to import agent '%s' from '%s.%s': %s", name, desc.module, desc.entry_func, e)
            return None

    @property
    def divisions(self) -> List[str]:
        """List of unique division names."""
        return sorted({a.division for a in self._agents.values() if a.enabled})


_global_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Return the global AgentRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry()
    return _global_registry
