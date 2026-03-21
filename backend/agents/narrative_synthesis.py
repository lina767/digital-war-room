"""
Cross-stream narrative synthesis: one cohesive causal story from all agent outputs.

Complements per-agent scores with an LLM-written chain of reasoning (e.g. markets → SIGINT → chokepoints).
"""

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

_MAX_NARRATIVE_PAYLOAD_CHARS = 120_000

_NARRATIVE_SYSTEM = """You are an intelligence analyst writing a single cohesive operational narrative.

Task: Explain how the intelligence streams CONNECT — not a list of 13 separate scores. Use causal language
(therefore, meanwhile, which suggests, reinforcing, at the same time). You may use arrows "→" between clauses
when it improves clarity.

Rules:
- Write in English only (no German or other languages).
- 4–8 short sentences OR 2–3 short paragraphs; plain text only (no JSON, no markdown headings).
- Name streams when relevant: FININT, SIGINT, NEWS, GEOINT, SATINTEL, SOCMINT, TECHINT, CYBER, ENERGY, PROTEST,
  DIPLO, PROXIMITY, CHOKEPOINT, and Signal Framework (payload key "narrative") when present.
- Tie highest-impact signals to the conflict context; mention obvious contradictions briefly if data supports it."""

_AGENT_ORDER = (
    "finint",
    "sigint",
    "news",
    "geoint",
    "satintel",
    "socmint",
    "techint",
    "cyber",
    "energy",
    "protest",
    "diplo",
    "proximity",
    "narrative",
    "chokepoint",
)


def _fallback_narrative(agent_outputs: Dict[str, Any]) -> str:
    """Deterministic recap when LLM is unavailable."""
    conflict = str(agent_outputs.get("conflict") or "theater").strip() or "theater"
    scores = agent_outputs.get("agent_scores")
    if not isinstance(scores, dict):
        return f"{conflict}: Multi-stream assessment pending; per-agent summaries were not available for a connected narrative."

    ranked = sorted(
        ((k, float(v)) for k, v in scores.items() if isinstance(v, (int, float))),
        key=lambda x: -x[1],
    )[:5]
    if not ranked:
        return f"{conflict}: Insufficient scored streams to build a cross-stream story."

    parts = [f"{conflict}: strongest signals - " + ", ".join(f"{k} ({v:.0f})" for k, v in ranked[:3])]
    for name in ("finint", "sigint", "chokepoint", "energy"):
        blob = agent_outputs.get(name)
        if isinstance(blob, dict):
            s = blob.get("summary")
            if isinstance(s, str) and s.strip():
                parts.append(f"{name.upper()}: {s.strip()[:220]}{'…' if len(s) > 220 else ''}")
                break
    return " ".join(parts)


def synthesize_narrative(agent_outputs: Dict[str, Any]) -> str:
    """
    Turn multi-agent JSON into one cohesive causal story in English (Claude Haiku by default; fallback on error).

    Expected shape: same as CEO supervisor payload — conflict, threat_level, composite_score, agent_scores,
    and per-agent compact dicts (finint, sigint, news, ...).
    """
    try:
        from .llm import call_llm, get_model_name, require_api_key

        require_api_key()
    except Exception as e:
        logger.debug("Narrative synthesis skipped (no API / key): %s", e)
        return _fallback_narrative(agent_outputs)

    slim: Dict[str, Any] = {
        "conflict": agent_outputs.get("conflict"),
        "composite_score": agent_outputs.get("composite_score"),
        "threat_level": agent_outputs.get("threat_level"),
        "division_composite_score": agent_outputs.get("division_composite_score"),
        "division_scores": agent_outputs.get("division_scores"),
        "agent_scores": agent_outputs.get("agent_scores"),
        "acled_reference_analyses": agent_outputs.get("acled_reference_analyses"),
    }
    for k in _AGENT_ORDER:
        if k in agent_outputs:
            slim[k] = agent_outputs[k]

    user_json = json.dumps(slim, default=str)
    if len(user_json) > _MAX_NARRATIVE_PAYLOAD_CHARS:
        user_json = user_json[:_MAX_NARRATIVE_PAYLOAD_CHARS]

    # Default: agent role = Claude Haiku on Anthropic (see llm.get_model_name("agent")).
    model_env = (os.getenv("NARRATIVE_SYNTHESIS_MODEL") or "").strip()
    model = model_env or get_model_name("agent")

    try:
        raw = call_llm(
            system=_NARRATIVE_SYSTEM,
            user_content=f"PAYLOAD_JSON:\n{user_json}",
            model=model,
            temperature=0.25,
            max_tokens=900,
        )
    except Exception as e:
        logger.warning("Narrative synthesis LLM failed: %s", e)
        return _fallback_narrative(agent_outputs)

    text = (raw or "").strip()
    if not text:
        return _fallback_narrative(agent_outputs)
    # Strip accidental code fences
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text[:6000]
