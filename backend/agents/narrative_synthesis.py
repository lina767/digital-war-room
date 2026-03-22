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

_NARRATIVE_SYSTEM = """You are an intelligence analyst writing one cohesive operational narrative for decision-makers.

Structure (follow this flow):
1) Open with the current situation in one or two sentences (what is happening in the theater).
2) Explain how the main streams reinforce or qualify each other — not a list of separate scores. Use causal
   language: therefore, meanwhile, which suggests, in parallel, reinforcing, offsetting. Arrows "→" between
   clauses are fine when they aid scanning.
3) Close with implications or what to watch next (one sentence), tied to the conflict.

Formatting:
- Write in English only (no German or other languages).
- Use 2–4 short paragraphs separated by a blank line between paragraphs (double newline in plain text).
- Each paragraph: 2–4 sentences. No bullet lists, no markdown headings, no JSON.
- Name streams when useful: FININT, SIGINT, NEWS, GEOINT, SATINTEL, SOCMINT, TECHINT, CYBER, ENERGY, PROTEST,
  DIPLO, PROXIMITY, CHOKEPOINT, Signal Framework (payload key "narrative") when present.
- If two signals contradict, say so briefly and which stream is softer evidence.
- If PAYLOAD_JSON includes "degraded_agents" (non-empty), name those streams and clarify that low scores there reflect missing feeds, not necessarily calm conditions.
- Stay under ~450 words."""

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

    parts = [
        f"{conflict}: the strongest scored streams right now are "
        + ", ".join(f"{k} ({v:.0f})" for k, v in ranked[:3])
        + "."
    ]
    for name in ("finint", "sigint", "chokepoint", "energy"):
        blob = agent_outputs.get(name)
        if isinstance(blob, dict):
            s = blob.get("summary")
            if isinstance(s, str) and s.strip():
                excerpt = s.strip()[:220] + ("…" if len(s) > 220 else "")
                parts.append(f"From {name.upper()}, the picture is: {excerpt}")
                break
    return "\n\n".join(parts)


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
        "agent_data_confidence": agent_outputs.get("agent_data_confidence"),
        "degraded_agents": agent_outputs.get("degraded_agents"),
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
