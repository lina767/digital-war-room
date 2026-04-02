"""CEO LLM synthesis: model routing, retries, JSON parse."""

import logging
import os
from typing import Any, Dict, List, Tuple

from .ceo_prompt import CEO_SYSTEM_PROMPT, truncate_supervisor_json
from .ceo_response import normalize_finding_confidence, normalize_next_steps, normalize_root_cause_suggestions
from .ceo_scoring import agents_seem_contradictory

logger = logging.getLogger(__name__)


def run_ceo_llm_synthesis(
    *,
    summary: str,
    threat_level: str,
    key_findings: List[str],
    key_findings_context: List[str],
    key_findings_confidence: List[str],
    root_cause_suggestions: List[Dict[str, str]],
    scenarios: List[Any],
    supervisor_payload: Dict[str, Any],
    agent_scores_list: List[float],
) -> Tuple[
    List[str],
    List[str],
    List[str],
    List[Dict[str, Any]],
    List[Dict[str, str]],
    List[Any],
    str,
    str,
    Dict[str, Any],
]:
    """Call supervisor LLM with retry/fallback models. Returns updated fields and synthesis_meta."""
    synthesis_meta: Dict[str, Any] = {"mode": "rule_based", "reason": "llm_not_attempted"}

    try:
        from .llm import call_llm, get_model_name, require_api_key
        from .utils import parse_llm_json

        require_api_key()

        use_fallback = os.getenv("USE_SUPERVISOR_FALLBACK_MODEL", "false").strip().lower() in ("1", "true", "yes")
        complex_case = use_fallback and agents_seem_contradictory(agent_scores_list)

        user_json = truncate_supervisor_json(supervisor_payload)

        tried_models: List[str] = []
        parse_error: str | None = None
        model_candidates = []
        if complex_case:
            model_candidates.append(get_model_name("supervisor_fallback"))
            model_candidates.append(get_model_name("supervisor_routine"))
        else:
            model_candidates.append(get_model_name("supervisor_routine"))
            model_candidates.append(get_model_name("supervisor_fallback"))

        kf = list(key_findings)
        kfc = list(key_findings_context)
        kfconf = list(key_findings_confidence)
        next_steps = []
        rcs = list(root_cause_suggestions)
        scen = list(scenarios)
        summ = summary
        tl = threat_level

        for model in model_candidates:
            if not model or model in tried_models:
                continue
            tried_models.append(model)
            raw = None
            llm_error: Exception | None = None
            for _ in range(3):
                try:
                    raw = call_llm(
                        system=CEO_SYSTEM_PROMPT,
                        user_content=user_json,
                        model=model,
                        temperature=0.1,
                    )
                    llm_error = None
                    break
                except Exception as e:  # pragma: no cover - retry path is integration/runtime dependent
                    llm_error = e
            if llm_error is not None:
                parse_error = f"llm_error:{type(llm_error).__name__}:{model}"
                continue
            parsed = parse_llm_json(raw) if raw else None
            if not isinstance(parsed, dict):
                parse_error = f"invalid_json_from_model:{model}"
                continue

            kf = list(parsed.get("key_findings") or [])
            kfc = list(parsed.get("key_findings_context") or [])
            raw_conf = parsed.get("key_findings_confidence")
            if isinstance(raw_conf, list):
                kfconf = [normalize_finding_confidence(x) for x in raw_conf]
            else:
                kfconf = []
            next_steps = normalize_next_steps(parsed.get("next_steps"))
            rcs = normalize_root_cause_suggestions(parsed.get("root_cause_suggestions"))
            scen = list(parsed.get("scenarios") or [])
            summ = str(parsed.get("summary", summ))
            if parsed.get("threat_level"):
                tl = str(parsed["threat_level"])
            synthesis_meta = {"mode": "llm", "model": model, "tried_models": tried_models}
            return kf, kfc, kfconf, next_steps, rcs, scen, summ, tl, synthesis_meta

        synthesis_meta = {
            "mode": "rule_based",
            "reason": parse_error or "empty_llm_response",
            "tried_models": tried_models,
        }
        return kf, kfc, kfconf, next_steps, rcs, scen, summ, tl, synthesis_meta

    except Exception as e:
        logger.warning("CEO LLM synthesis failed: %s — using rule-based fallback", e)
        synthesis_meta = {"mode": "rule_based", "reason": f"llm_error:{type(e).__name__}"}
        return (
            key_findings,
            key_findings_context,
            key_findings_confidence,
            [],
            root_cause_suggestions,
            scenarios,
            summary,
            threat_level,
            synthesis_meta,
        )
