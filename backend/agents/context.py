"""
AgentContext – Shared context for closer agent collaboration.

When USE_AGENT_HANDOFF is enabled, the DAG runs agents in two waves:
- Wave 1 (foundation): finint, sigint, news, diplo, techint, cyber run in parallel.
- Context is built from their results (summaries, regions, entities, key findings).
- Wave 2 (context-aware): geoint, socmint, energy, proximity, chokepoint, narrative
  receive this context and can focus queries (e.g. GEOINT on SIGINT regions, NEWS on FININT cues).

Agents that support context accept an optional second argument: run_*_agent(conflict, context=None).

Peer data beyond the compact AgentContext: while a DAG node runs, use
``analysis_run_state.get_peer_result("sigint")`` or ``get_peers_snapshot()`` to read other
nodes' outputs from the shared ResultStore — no CEO/supervisor round-trip required; only
nodes that have already completed and written to the store are readable (DAG order).

The orchestrator also passes ``peers={...}`` into every ``run_*_agent`` (optional kwarg) with
the same non-None snapshot for convenience.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Shared context passed to agents in wave 2 (handoff mode)."""

    # Short summaries from wave-1 agents for cross-reference
    peer_summaries: Dict[str, str] = Field(default_factory=dict)
    # Regions to focus on (e.g. from SIGINT aircraft/ships: {"region": "Gulf", "lat": 27, "lon": 53})
    focus_regions: List[Dict[str, Any]] = Field(default_factory=list)
    # Entity names from NER or previous run (e.g. "IRGC", "Hezbollah")
    focus_entities: List[str] = Field(default_factory=list)
    # Key findings so far (from wave 1) so wave-2 agents can corroborate or deepen
    key_findings_so_far: List[str] = Field(default_factory=list)
    # Escalation-relevant headlines or signals (e.g. from NEWS) for SOCMINT/NEWS focus
    escalation_signals: List[str] = Field(default_factory=list)

    def summary_for_agent(self, agent_name: str, max_chars: int = 400) -> str:
        """Single string describing what other agents found, for use in prompts or query focus."""
        parts = []
        for peer, summary in self.peer_summaries.items():
            if peer == agent_name or not summary:
                continue
            s = summary[:150] + "..." if len(summary) > 150 else summary
            parts.append(f"{peer}: {s}")
        if self.focus_regions:
            parts.append("Focus regions: " + ", ".join(str(r.get("region", r)) for r in self.focus_regions[:5]))
        if self.focus_entities:
            parts.append("Entities: " + ", ".join(self.focus_entities[:10]))
        if self.key_findings_so_far:
            parts.append("Findings: " + " | ".join(self.key_findings_so_far[:3]))
        text = " ".join(parts)
        return text[:max_chars] if len(text) > max_chars else text


# Agent names for two-phase handoff (must match registry).
WAVE1_AGENTS = ["finint", "sigint", "news", "diplo", "techint", "cyber"]
WAVE2_AGENTS = [
    "geoint",
    "satintel",
    "socmint",
    "energy",
    "proximity",
    "chokepoint",
    "pentagon",
    "narrative",
]


def build_context_from_results(wave1_results: Dict[str, Any]) -> "AgentContext":
    """Build AgentContext from wave-1 agent results for wave-2 handoff."""
    peer_summaries = {}
    for name in WAVE1_AGENTS:
        data = wave1_results.get(name) or {}
        if not isinstance(data, dict):
            continue
        summary = (data.get("summary") or "").strip()
        if summary:
            peer_summaries[name] = summary[:500]

    focus_regions = []
    sigint_data = wave1_results.get("sigint") or {}
    for item in (sigint_data.get("aircraft") or [])[:10]:
        if not isinstance(item, dict) or "error" in item:
            continue
        try:
            lat, lon = item.get("lat"), item.get("lon")
            if lat is None or lon is None:
                continue
            lat_f, lon_f = float(lat), float(lon)
            region = item.get("region") or item.get("source") or "unknown"
            focus_regions.append({"region": region, "lat": lat_f, "lon": lon_f})
        except (TypeError, ValueError):
            continue
    for item in (sigint_data.get("ships") or [])[:5]:
        if not isinstance(item, dict) or "error" in item:
            continue
        try:
            lat, lon = item.get("lat"), item.get("lon")
            if lat is None or lon is None:
                continue
            focus_regions.append({"region": "ship", "lat": float(lat), "lon": float(lon)})
        except (TypeError, ValueError):
            continue

    escalation_signals = []
    for art in (wave1_results.get("news") or {}).get("articles") or []:
        if isinstance(art, dict) and art.get("escalation_headline"):
            title = (art.get("title") or "").strip()
            if title:
                escalation_signals.append(title[:120])

    key_findings_so_far: List[str] = []
    news_data = wave1_results.get("news") or {}
    for art in (news_data.get("articles") or [])[:2]:
        if isinstance(art, dict) and art.get("title"):
            key_findings_so_far.append(f"NEWS: {art.get('title', '')[:80]}")
    sigint_ac = sigint_data.get("aircraft") or []
    if sigint_ac:
        key_findings_so_far.append(f"SIGINT: {len(sigint_ac)} aircraft in region")
    if sigint_data.get("conflict_reports") or []:
        key_findings_so_far.append("SIGINT: conflict intel reports present")

    return AgentContext(
        peer_summaries=peer_summaries,
        focus_regions=focus_regions[:15],
        focus_entities=[],  # Can be filled from NER in post-processing in a later step
        key_findings_so_far=key_findings_so_far[:8],
        escalation_signals=escalation_signals[:5],
    )
