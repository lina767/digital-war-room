"""
Data Analyst: single comprehensive intelligence analysis via Anthropic tool_use.

Replaces the scattered LLM calls (supervisor synthesis, assessment, narrative,
briefing interpretation) with one structured call. The output schema is enforced
via tool_use + tool_choice so the model must return valid structured data.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic output schema (becomes the tool's input_schema) ─────────────


class AnalystNextStep(BaseModel):
    action: str = Field(description="Concrete, specific action to take")
    owner: str = Field(description="analyst | ops | exec")
    time_horizon: str = Field(description="now | 24h | 7d")
    why: str = Field(description="Rationale for urgency/priority")
    source_refs: List[str] = Field(
        default_factory=list,
        description="URLs from the payload that support this action",
    )
    confidence: str = Field(description="high | medium | low")


class AnalystScenario(BaseModel):
    title: str
    probability: str = Field(description="Qualitative: likely | possible | unlikely")
    description: str
    indicators: List[str] = Field(
        default_factory=list,
        description="Observable signals that would confirm this scenario",
    )


class AnalystRootCause(BaseModel):
    signal: str = Field(description="The observable data point")
    likely_cause: str = Field(description="Hypothesised driver behind the signal")
    confidence: str = Field(description="high | medium | low")


class AnalystAssessment(BaseModel):
    situation: str = Field(description="2-3 sentences: what is happening")
    significance: str = Field(description="Why it matters for the stakeholder")
    trajectory_24h: str = Field(description="24-hour outlook")
    trajectory_7d: str = Field(description="7-day outlook")
    trajectory_30d: str = Field(description="30-day outlook")
    information_gaps: List[str] = Field(
        default_factory=list,
        description="What we do not know + where to look",
    )


class AnalystOutput(BaseModel):
    """Complete analysis output. Every field is required."""

    summary: str = Field(description="2-3 sentence BLUF (Bottom Line Up Front)")
    narrative_story: str = Field(
        description=(
            "2-4 short paragraphs. Causal cross-stream narrative for decision-makers. "
            "Use stream names (FININT, SIGINT, etc.) and causal language (therefore, "
            "meanwhile, which suggests). No bullet lists, no markdown."
        )
    )
    briefing_interpretation: str = Field(
        description=(
            "1-2 paragraphs: executive interpretation of the briefing. "
            "What does this mean for the stakeholder? What should they watch?"
        )
    )
    key_findings: List[str] = Field(
        description="6-15 concise finding strings, most significant first"
    )
    key_findings_confidence: List[str] = Field(
        description="Same length as key_findings; each value high | medium | low"
    )
    next_steps: List[AnalystNextStep] = Field(
        description="5-10 specific, time-bounded action items"
    )
    root_cause_suggestions: List[AnalystRootCause] = Field(
        default_factory=list,
        description="Up to 5 signal-to-driver hypotheses",
    )
    scenarios: List[AnalystScenario] = Field(
        description="2-4 forward-looking scenarios"
    )
    assessment: AnalystAssessment
    data_quality_notes: List[str] = Field(
        default_factory=list,
        description="Caveats: degraded feeds, missing data, low sample sizes, correlation-vs-causation warnings",
    )


# ── System prompt ────────────────────────────────────────────────────────

DATA_ANALYST_SYSTEM = """\
You are a senior intelligence data analyst. You receive structured data from \
multiple OSINT collection streams and produce a comprehensive assessment.

Your workflow:
1. INSPECT the data: note which streams are active vs degraded, coverage gaps, \
data freshness. Always look before you analyze.
2. NOTE data quality issues: degraded feeds (low scores may mean missing data, \
not safety), contradictions between streams, low-confidence signals. List these \
in data_quality_notes.
3. ANALYZE cross-stream patterns: what do the streams collectively tell us? \
Use causal reasoning — e.g. market moves (FININT) correlated with military \
signals (SIGINT) correlated with chokepoint disruption risk. Name streams \
explicitly. When two streams contradict, say so and state which is softer evidence.
4. PRODUCE findings with explicit confidence. A finding supported by 3+ streams \
is "high"; 2 streams is "medium"; single-stream is "low". Never invent sources.
5. DEFAULT to clear, readable analysis. A simple finding with evidence beats a \
speculative narrative. Plain language with caveats (sample size, missing data, \
correlation-vs-causation) over clever synthesis.

Streams available (may or may not have data):
- FININT: Markets, oil, sanctions, Polymarket prediction markets
- SIGINT: Military aircraft/vessels, conflict reports
- NEWS: Open-source media articles with sentiment
- GEOINT: Satellite thermal anomalies (FIRMS)
- SATINTEL: Sentinel Hub/Copernicus imagery
- SOCMINT: Social media (Telegram, Reddit, RSS)
- TECHINT: Tech indicators, export controls, internet outages (IODA)
- CYBER: CISA KEV, threat intel, OTX pulses
- ENERGY: Commodities (Brent, WTI), food prices, EU gas storage
- DIPLO: OFAC/EU sanctions, UN/ICJ diplomatic signals
- PROXIMITY: Strike-civilian infrastructure correlation
- CHOKEPOINT: Maritime chokepoints (Hormuz, Bab el-Mandeb, Suez)
- PENTAGON: Informal DC venue proxies (anecdotal only, never treat as confirmed)
- Signal Framework (key "narrative"): state vs exile media comparison

When Polymarket data is present, mention explicitly in summary or key_findings \
(probabilities + titles). Phrase as market-priced expectations, not confirmed events.

When "degraded_agents" is non-empty, you MUST name those streams and warn that \
scores may understate risk.

When "finding_signal_gate.accepted" is present, use those as a high-signal \
shortlist for key_findings.

Respond by calling the emit_analysis tool with the complete analysis."""


# ── Main entry point ─────────────────────────────────────────────────────


def run_data_analyst(
    *,
    conflict: str,
    supervisor_payload: Dict[str, Any],
    synthesis_score: float,
    threat_level: str,
    degraded_agents: List[str],
    finding_gate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the Data Analyst via Anthropic tool_use. Returns a dict matching AnalystOutput fields.

    On any failure, returns a minimal rule-based fallback so the pipeline never breaks.
    """
    from .ceo_prompt import truncate_supervisor_json
    from .ceo_response import build_rule_based_ceo_summary
    from .llm import LLMCreditExhaustedError, call_llm_tool_use, require_api_key

    try:
        require_api_key()
    except RuntimeError:
        logger.warning("Data Analyst: no API key configured, using rule-based fallback")
        return _build_fallback(conflict, synthesis_score, threat_level, degraded_agents)

    payload_json = truncate_supervisor_json(supervisor_payload)

    try:
        result = call_llm_tool_use(
            system=DATA_ANALYST_SYSTEM,
            user_content=payload_json,
            output_schema=AnalystOutput,
            tool_name="emit_analysis",
            tool_description="Emit the complete structured intelligence analysis.",
            max_tokens=int(os.getenv("DATA_ANALYST_MAX_TOKENS", "8192")),
        )

        if not isinstance(result.get("key_findings"), list) or not result.get("summary"):
            logger.warning("Data Analyst: tool_use returned incomplete output, using fallback")
            return _build_fallback(conflict, synthesis_score, threat_level, degraded_agents)

        # Normalize next_steps to the format assemble_ceo_response expects
        next_steps = result.get("next_steps") or []
        result["next_steps"] = [
            {
                "action": ns.get("action", ""),
                "owner": ns.get("owner", "analyst"),
                "time_horizon": ns.get("time_horizon", "24h"),
                "why": ns.get("why", ""),
                "source_refs": ns.get("source_refs", []),
                "confidence": ns.get("confidence", "medium"),
            }
            for ns in next_steps
            if isinstance(ns, dict)
        ]

        # Normalize root_cause_suggestions
        rcs = result.get("root_cause_suggestions") or []
        result["root_cause_suggestions"] = [
            {
                "signal": rc.get("signal", ""),
                "likely_cause": rc.get("likely_cause", ""),
                "confidence": rc.get("confidence", "medium"),
            }
            for rc in rcs
            if isinstance(rc, dict)
        ]

        # Normalize scenarios
        scenarios = result.get("scenarios") or []
        result["scenarios"] = [
            {
                "title": sc.get("title", ""),
                "probability": sc.get("probability", "possible"),
                "description": sc.get("description", ""),
                "indicators": sc.get("indicators", []),
            }
            for sc in scenarios
            if isinstance(sc, dict)
        ]

        result["_meta"] = {"mode": "data_analyst_tool_use"}
        return result

    except LLMCreditExhaustedError:
        logger.error("Data Analyst: credits exhausted, using rule-based fallback")
        return _build_fallback(conflict, synthesis_score, threat_level, degraded_agents)
    except Exception as exc:
        logger.error("Data Analyst call failed: %s", exc, exc_info=True)
        return _build_fallback(conflict, synthesis_score, threat_level, degraded_agents)


def _build_fallback(
    conflict: str,
    synthesis_score: float,
    threat_level: str,
    degraded_agents: List[str],
) -> Dict[str, Any]:
    """Deterministic fallback when the LLM call fails."""
    from .ceo_response import build_rule_based_ceo_summary

    summary = build_rule_based_ceo_summary(
        conflict, synthesis_score, threat_level, {}, degraded_agents=degraded_agents
    )
    degraded_note = (
        f"Degraded feeds ({', '.join(degraded_agents[:6])}): low scores may reflect missing data, not safety."
        if degraded_agents
        else ""
    )
    return {
        "summary": summary,
        "narrative_story": "",
        "briefing_interpretation": "",
        "key_findings": [],
        "key_findings_confidence": [],
        "next_steps": [
            {
                "action": "Verify top escalatory claims against primary sources.",
                "owner": "analyst",
                "time_horizon": "now",
                "why": "Rule-based fallback: LLM synthesis unavailable.",
                "source_refs": [],
                "confidence": "medium",
            },
        ],
        "root_cause_suggestions": [],
        "scenarios": [],
        "assessment": {
            "situation": summary,
            "significance": "",
            "trajectory_24h": "",
            "trajectory_7d": "",
            "trajectory_30d": "",
            "information_gaps": [],
        },
        "data_quality_notes": [degraded_note] if degraded_note else [],
        "_meta": {"mode": "rule_based_fallback"},
    }
