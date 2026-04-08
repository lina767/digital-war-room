"""
Haiku Service — Central wrapper for Claude Haiku 4.5 calls (optional per-call model override).

All agent tasks requiring language understanding (translation, sentiment, NER,
classification, summarization) route through this service. Provides:
- Call counter and budget tracker (real usage from API response)
- Per-run limits (configurable via env)
- Graceful degradation (errors → None, never crashes the caller)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

HAIKU_MODEL = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
HAIKU_MAX_CALLS_PER_RUN = int(os.getenv("HAIKU_MAX_CALLS_PER_RUN", "150"))
HAIKU_MAX_TRANSLATION_PER_RUN = int(os.getenv("HAIKU_MAX_TRANSLATION_PER_RUN", "20"))
HAIKU_MAX_SENTIMENT_PER_RUN = int(os.getenv("HAIKU_MAX_SENTIMENT_PER_RUN", "40"))
HAIKU_MAX_NER_PER_RUN = int(os.getenv("HAIKU_MAX_NER_PER_RUN", "40"))
HAIKU_MAX_CLASSIFY_PER_RUN = int(os.getenv("HAIKU_MAX_CLASSIFY_PER_RUN", "30"))
HAIKU_MAX_SUMMARIZE_PER_RUN = int(os.getenv("HAIKU_MAX_SUMMARIZE_PER_RUN", "20"))
HAIKU_MAX_DOCQA_PER_RUN = int(os.getenv("HAIKU_MAX_DOCQA_PER_RUN", "10"))
HAIKU_MAX_ANALYST_SUMMARY_PER_RUN = int(os.getenv("HAIKU_MAX_ANALYST_SUMMARY_PER_RUN", "15"))
HAIKU_MONTHLY_BUDGET = float(os.getenv("HAIKU_MONTHLY_BUDGET", "20.0"))

# Pricing per million tokens (Haiku 4.5)
_INPUT_COST_PER_MTOK = 1.0
_OUTPUT_COST_PER_MTOK = 5.0
# Sonnet-class (e.g. claude-sonnet-4-6) — approximate; used when model id contains "sonnet"
_SONNET_INPUT_COST_PER_MTOK = float(os.getenv("SONNET_INPUT_COST_PER_MTOK", "3.0"))
_SONNET_OUTPUT_COST_PER_MTOK = float(os.getenv("SONNET_OUTPUT_COST_PER_MTOK", "15.0"))

# ── Budget Tracker ───────────────────────────────────────────────────────────

_monthly_input_tokens = 0
_monthly_output_tokens = 0
_monthly_cost_usd = 0.0
_budget_month: str = ""

# Per-run counters (reset via reset_run_counters)
_run_call_count = 0
_run_translation_count = 0
_run_sentiment_count = 0
_run_ner_count = 0
_run_classify_count = 0
_run_summarize_count = 0
_run_docqa_count = 0
_run_analyst_summary_count = 0
_run_input_tokens = 0
_run_output_tokens = 0
_run_cost_usd = 0.0

# Per-agent token attribution (Haiku calls only; keys e.g. news, cyber, diplo)
_run_tokens_by_agent: Dict[str, Dict[str, int]] = {}
_monthly_tokens_by_agent: Dict[str, Dict[str, int]] = {}

# Tracks whether a Haiku error occurred in this run (for batch-fallback logic)
_run_haiku_failed = False


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _ensure_month():
    """Reset monthly counters if the month has changed."""
    global _budget_month, _monthly_input_tokens, _monthly_output_tokens, _monthly_cost_usd
    m = _current_month()
    if _budget_month != m:
        _budget_month = m
        _monthly_input_tokens = 0
        _monthly_output_tokens = 0
        _monthly_cost_usd = 0.0
        global _monthly_tokens_by_agent
        _monthly_tokens_by_agent = {}


def _mtok_rates_for_model(model: str) -> tuple[float, float]:
    """Return (input_per_mtok, output_per_mtok) for budget logging."""
    m = (model or "").lower()
    if "sonnet" in m:
        return _SONNET_INPUT_COST_PER_MTOK, _SONNET_OUTPUT_COST_PER_MTOK
    return _INPUT_COST_PER_MTOK, _OUTPUT_COST_PER_MTOK


def _bump_agent_tokens(agent: str, input_tokens: int, output_tokens: int) -> None:
    global _run_tokens_by_agent, _monthly_tokens_by_agent
    if agent not in _run_tokens_by_agent:
        _run_tokens_by_agent[agent] = {"in": 0, "out": 0}
    _run_tokens_by_agent[agent]["in"] += input_tokens
    _run_tokens_by_agent[agent]["out"] += output_tokens
    if agent not in _monthly_tokens_by_agent:
        _monthly_tokens_by_agent[agent] = {"in": 0, "out": 0}
    _monthly_tokens_by_agent[agent]["in"] += input_tokens
    _monthly_tokens_by_agent[agent]["out"] += output_tokens


def _increment_usage(
    input_tokens: int,
    output_tokens: int,
    usage_agent: str = "other",
    *,
    model: Optional[str] = None,
) -> None:
    """Track real token usage from the API response."""
    global _monthly_input_tokens, _monthly_output_tokens, _monthly_cost_usd
    global _run_call_count, _run_input_tokens, _run_output_tokens, _run_cost_usd
    _ensure_month()
    _monthly_input_tokens += input_tokens
    _monthly_output_tokens += output_tokens
    in_rate, out_rate = _mtok_rates_for_model(model or HAIKU_MODEL)
    cost = (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
    _monthly_cost_usd += cost
    _run_call_count += 1
    _run_input_tokens += input_tokens
    _run_output_tokens += output_tokens
    _run_cost_usd += cost
    _bump_agent_tokens(usage_agent or "other", input_tokens, output_tokens)

    if _monthly_cost_usd >= HAIKU_MONTHLY_BUDGET * 0.8:
        logger.warning(
            "[haiku] Monthly budget %.0f%% used ($%.2f / $%.2f)",
            (_monthly_cost_usd / HAIKU_MONTHLY_BUDGET) * 100,
            _monthly_cost_usd,
            HAIKU_MONTHLY_BUDGET,
        )


def _check_budget() -> bool:
    """Return True if budget still allows calls."""
    _ensure_month()
    return _monthly_cost_usd < HAIKU_MONTHLY_BUDGET


def reset_run_counters():
    """Call at the start of each 6h analysis run."""
    global _run_call_count, _run_translation_count, _run_sentiment_count, _run_ner_count
    global _run_classify_count, _run_summarize_count, _run_docqa_count, _run_analyst_summary_count
    global _run_input_tokens, _run_output_tokens, _run_cost_usd, _run_haiku_failed, _run_tokens_by_agent
    _run_call_count = 0
    _run_translation_count = 0
    _run_sentiment_count = 0
    _run_ner_count = 0
    _run_classify_count = 0
    _run_summarize_count = 0
    _run_docqa_count = 0
    _run_analyst_summary_count = 0
    _run_input_tokens = 0
    _run_output_tokens = 0
    _run_cost_usd = 0.0
    _run_haiku_failed = False
    _run_tokens_by_agent = {}


def is_haiku_failed() -> bool:
    """True if Haiku encountered an error during this run (batch-fallback signal)."""
    return _run_haiku_failed


def log_run_stats():
    """Log summary at the end of each run."""
    _ensure_month()
    run_cost = _run_cost_usd
    logger.info(
        "[haiku] Run stats: %d calls, %d input tokens, %d output tokens, ~$%.4f. Month total: ~$%.2f / $%.2f",
        _run_call_count,
        _run_input_tokens,
        _run_output_tokens,
        run_cost,
        _monthly_cost_usd,
        HAIKU_MONTHLY_BUDGET,
    )
    try:
        from services.monitoring_store import record_haiku_daily

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        by_agent = {k: dict(v) for k, v in _run_tokens_by_agent.items()}
        record_haiku_daily(
            day=day,
            spend_usd=run_cost,
            input_tokens=_run_input_tokens,
            output_tokens=_run_output_tokens,
            by_agent=by_agent,
        )
    except Exception:
        pass


def get_haiku_metrics_for_api() -> Dict[str, Any]:
    """Token and spend snapshot for Agent Monitor (Haiku / Claude)."""
    _ensure_month()
    run_cost = _run_cost_usd
    return {
        "provider": "anthropic_haiku",
        "model": HAIKU_MODEL,
        "month_budget_usd": HAIKU_MONTHLY_BUDGET,
        "month_spent_usd": round(_monthly_cost_usd, 6),
        "month_input_tokens": _monthly_input_tokens,
        "month_output_tokens": _monthly_output_tokens,
        "month_by_agent": {k: dict(v) for k, v in _monthly_tokens_by_agent.items()},
        "last_run": {
            "input_tokens": _run_input_tokens,
            "output_tokens": _run_output_tokens,
            "estimated_cost_usd": round(run_cost, 8),
            "by_agent": {k: dict(v) for k, v in _run_tokens_by_agent.items()},
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _strip_json_block(raw: str) -> str:
    """Strip ```json ... ``` fencing that LLMs sometimes wrap around JSON output."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return cleaned


# ── Core API call ────────────────────────────────────────────────────────────


def _get_client():
    """Lazy-import and create Anthropic client."""
    from anthropic import Anthropic

    return Anthropic()


async def _call_haiku(
    system: str,
    user_content: str,
    max_tokens: int = 1024,
    *,
    usage_agent: str = "other",
    model: Optional[str] = None,
    bypass_per_run_call_limit: bool = False,
) -> Optional[str]:
    """
    Low-level Haiku call with budget/limit checks and usage tracking.
    Returns the text response or None on any failure.

    ``bypass_per_run_call_limit`` is used by dashboard chat (`analyst_summary` with
    ``skip_run_limits=True``) so a long analysis run does not exhaust
    ``HAIKU_MAX_CALLS_PER_RUN`` and block user-visible Q&A. Monthly budget still applies.
    """
    if not bypass_per_run_call_limit and _run_call_count >= HAIKU_MAX_CALLS_PER_RUN:
        logger.warning("[haiku] Run call limit reached (%d)", HAIKU_MAX_CALLS_PER_RUN)
        return None
    if not _check_budget():
        logger.warning("[haiku] Monthly budget exhausted")
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    effective_model = (model or HAIKU_MODEL).strip() or HAIKU_MODEL

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        client = _get_client()
        resp = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=effective_model,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                temperature=0,
                max_tokens=max_tokens,
            ),
        )
        _increment_usage(
            resp.usage.input_tokens,
            resp.usage.output_tokens,
            usage_agent,
            model=effective_model,
        )
        if resp.content:
            return resp.content[0].text
        return None
    except Exception as e:
        global _run_haiku_failed
        _run_haiku_failed = True
        logger.error("[haiku] API call failed: %s", e)
        return None


# ── Translation (Phase 1) ───────────────────────────────────────────────────

_TRANSLATE_SYSTEM = (
    "You are a professional Farsi-to-English translator specializing in "
    "geopolitical, military, and nuclear terminology. Translate the following "
    "Farsi text accurately. Preserve proper nouns (IRGC, Sepah, Basij, etc.) "
    "in their standard English transliterations. Maintain the tone and "
    "formality level of the original. Return ONLY the English translation."
)


async def translate_fa_en(text: str) -> Optional[str]:
    """
    Translate Farsi text to English using Haiku.
    Returns the English translation or None if translation fails or limits exceeded.
    """
    global _run_translation_count
    if not text or not text.strip():
        return None
    if _run_translation_count >= HAIKU_MAX_TRANSLATION_PER_RUN:
        logger.debug("[haiku] Translation limit reached (%d)", HAIKU_MAX_TRANSLATION_PER_RUN)
        return None

    result = await _call_haiku(_TRANSLATE_SYSTEM, text.strip(), max_tokens=2048, usage_agent="news")
    if result:
        _run_translation_count += 1
    return result


# ── Sentiment (Phase 2) ─────────────────────────────────────────────────────

_SENTIMENT_SYSTEM = (
    "You are a geopolitical context analyst. Analyze the sentiment of the following text "
    "in its original language (no translation needed). Detect irony, propaganda language, "
    "and diplomatic formulations. You understand Farsi, Arabic, English, and German natively.\n\n"
    "Return ONLY valid JSON:\n"
    '{"label": "positive" or "negative" or "neutral", "score": <float -1 to 1>, '
    '"confidence": <float 0 to 1>, "reasoning": "<one sentence>"}'
)


async def sentiment(text: str, lang: str = "auto") -> Optional[Dict[str, Any]]:
    """
    Multilingual sentiment analysis — HuggingFace first, Haiku fallback.
    Returns {"label", "score", "confidence", "reasoning"} or None.
    """
    global _run_sentiment_count
    if not text or not text.strip():
        return None

    # ── HuggingFace primary path (free, fast) ──
    try:
        from services.hf_service import sentiment_classify

        hf_result = await sentiment_classify(text)
        if hf_result and hf_result.get("label"):
            return {
                "label": hf_result["label"],
                "score": hf_result.get("score", 0),
                "confidence": hf_result.get("confidence", 0),
                "reasoning": "HF-classified",
            }
    except Exception as e:
        logger.debug("[haiku] HF sentiment fallthrough: %s", e)

    # ── Haiku fallback (only if HF unavailable) ──
    if _run_haiku_failed:
        return None
    if _run_sentiment_count >= HAIKU_MAX_SENTIMENT_PER_RUN:
        logger.debug("[haiku] Sentiment limit reached (%d)", HAIKU_MAX_SENTIMENT_PER_RUN)
        return None

    raw = await _call_haiku(_SENTIMENT_SYSTEM, text.strip()[:2000], max_tokens=256, usage_agent="news")
    if not raw:
        return None
    try:
        parsed = json.loads(_strip_json_block(raw))
        _run_sentiment_count += 1
        return {
            "label": parsed.get("label", "neutral"),
            "score": float(parsed.get("score", 0)),
            "confidence": float(parsed.get("confidence", 0)),
            "reasoning": parsed.get("reasoning", ""),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("[haiku] Sentiment response not valid JSON: %.100s", raw)
        return None


# ── NER (Phase 2) ───────────────────────────────────────────────────────────

_NER_SYSTEM = (
    "You are an OSINT entity extractor specializing in geopolitical, military, and nuclear domains. "
    "Extract named entities from the following text. Recognize not only standard PER/ORG/LOC, "
    "but also: weapon systems, military units, sanction programs, nuclear facilities, "
    "drone types, vessel names, aircraft.\n\n"
    "Entity types: PERSON, ORG, LOCATION, WEAPON_SYSTEM, MILITARY_UNIT, "
    "NUCLEAR_FACILITY, SANCTION_PROGRAM, VESSEL, AIRCRAFT\n\n"
    "Return ONLY a valid JSON array:\n"
    '[{"entity": "<name>", "type": "<TYPE>", "context": "<short context>"}]'
)


_DOMAIN_NER_KEYWORDS = [
    "missile", "drone", "s-300", "s-400", "patriot", "iron dome", "centrifuge",
    "enrichment", "reactor", "warhead", "battalion", "brigade", "division",
    "irgc", "quds", "basij", "hezbollah", "hamas", "houthi", "wagner",
    "vessel", "destroyer", "frigate", "carrier", "submarine", "tanker",
    "f-35", "su-35", "mig", "tu-95", "shahed", "predator", "reaper",
    "nuclear facility", "natanz", "fordow", "bushehr", "dimona",
]


def _needs_domain_ner(text: str) -> bool:
    """Check if text likely contains domain-specific entities that HF NER can't detect."""
    lower = text.lower()
    return any(kw in lower for kw in _DOMAIN_NER_KEYWORDS)


async def ner(text: str) -> Optional[List[Dict[str, str]]]:
    """
    Named Entity Recognition — HuggingFace first (PER/ORG/LOC), Haiku only for
    domain-specific types (WEAPON_SYSTEM, MILITARY_UNIT, NUCLEAR_FACILITY, etc.).
    Returns [{"entity", "type", "context"}] or None.
    """
    global _run_ner_count
    if not text or not text.strip():
        return None

    # ── HuggingFace primary path (free) ──
    hf_entities: Optional[List[Dict[str, str]]] = None
    try:
        from services.hf_service import ner_bulk

        hf_results = await ner_bulk([text.strip()[:3000]])
        if hf_results and hf_results[0]:
            hf_entities = [
                {"entity": e["entity"], "type": e["type"], "context": e.get("context", "")}
                for e in hf_results[0]
                if isinstance(e, dict) and e.get("entity")
            ]
    except Exception as e:
        logger.debug("[haiku] HF NER fallthrough: %s", e)

    if not _needs_domain_ner(text):
        if hf_entities is not None:
            return hf_entities if hf_entities else []

    # ── Haiku for domain-specific entity types ──
    if _run_haiku_failed:
        return hf_entities
    if _run_ner_count >= HAIKU_MAX_NER_PER_RUN:
        logger.debug("[haiku] NER limit reached (%d)", HAIKU_MAX_NER_PER_RUN)
        return hf_entities

    raw = await _call_haiku(_NER_SYSTEM, text.strip()[:3000], max_tokens=1024, usage_agent="news")
    if not raw:
        return hf_entities
    try:
        parsed = json.loads(_strip_json_block(raw))
        if isinstance(parsed, list):
            _run_ner_count += 1
            haiku_entities = [
                {
                    "entity": e.get("entity", ""),
                    "type": e.get("type", "MISC"),
                    "context": e.get("context", ""),
                }
                for e in parsed
                if isinstance(e, dict) and e.get("entity")
            ]
            # Merge: Haiku is authoritative for domain types, HF for standard types.
            if hf_entities:
                seen = {(e["entity"].lower(), e["type"]) for e in haiku_entities}
                for e in hf_entities:
                    if (e["entity"].lower(), e["type"]) not in seen:
                        haiku_entities.append(e)
            return haiku_entities
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("[haiku] NER response not valid JSON: %.100s", raw)
    return hf_entities


# ── Batch functions (Phase 2) ───────────────────────────────────────────────


async def batch_sentiment(texts: List[str]) -> List[Optional[Dict[str, Any]]]:
    """
    Run sentiment on multiple texts. If Haiku fails on the first call,
    switch entire batch to None (batch-fallback signal for the caller).
    """
    results: List[Optional[Dict[str, Any]]] = []
    for t in texts:
        if _run_haiku_failed:
            results.append(None)
            continue
        r = await sentiment(t)
        results.append(r)
    return results


async def batch_ner(texts: List[str]) -> List[Optional[List[Dict[str, str]]]]:
    """
    Run NER on multiple texts. If Haiku fails on the first call,
    switch entire batch to None (batch-fallback signal for the caller).
    """
    results: List[Optional[List[Dict[str, str]]]] = []
    for t in texts:
        if _run_haiku_failed:
            results.append(None)
            continue
        r = await ner(t)
        results.append(r)
    return results


# ── Zero-Shot Classification (Phase 3) ──────────────────────────────────────

_GEOPOLITICAL_CATEGORIES = [
    "military_conflict",
    "nuclear_proliferation",
    "sanctions_trade",
    "diplomacy",
    "cyber_warfare",
    "energy_disruption",
    "humanitarian_crisis",
    "civil_unrest",
    "maritime_security",
    "other",
]

_CLASSIFY_SYSTEM = (
    "You are a geopolitical intelligence classifier. Classify the following text "
    "into exactly ONE of these categories:\n" + ", ".join(_GEOPOLITICAL_CATEGORIES) + "\n\n"
    "Return ONLY valid JSON:\n"
    '{"category": "<category>", "confidence": <float 0 to 1>}'
)


_KEYWORD_RULES: Dict[str, List[str]] = {
    "military_conflict": [
        "military", "troops", "strike", "attack", "war", "drone", "missile",
        "combat", "airstrike", "battle", "offensive", "shelling", "artillery",
        "airbase", "deployment", "killed", "soldiers", "incursion", "clashes",
        "bombardment", "mortar", "armor", "tank", "fighter jet",
    ],
    "nuclear_proliferation": [
        "nuclear", "uranium", "centrifuge", "enrichment", "iaea", "reactor",
        "warhead", "proliferation", "plutonium", "atomic", "fissile",
    ],
    "sanctions_trade": [
        "sanction", "embargo", "ofac", "trade restriction", "asset freeze",
        "blacklist", "designation", "trade ban", "treasury", "sdn list",
    ],
    "diplomacy": [
        "diplomat", "ambassador", "treaty", "negotiation", "summit",
        "bilateral", "multilateral", "un resolution", "peace talk",
        "ceasefire", "accord", "envoy", "foreign minister",
    ],
    "cyber_warfare": [
        "cyber", "hack", "ransomware", "malware", "ddos", "phishing",
        "apt", "breach", "exploit", "zero-day", "botnet",
    ],
    "energy_disruption": [
        "oil price", "gas pipeline", "opec", "refinery", "fuel shortage",
        "energy crisis", "power grid", "blackout", "lng", "oil tanker",
    ],
    "humanitarian_crisis": [
        "humanitarian", "refugee", "displaced", "famine", "aid",
        "relief", "un aid", "idp", "food insecurity", "cholera",
    ],
    "civil_unrest": [
        "protest", "riot", "demonstration", "uprising", "unrest",
        "opposition", "crackdown", "tear gas", "curfew",
    ],
    "maritime_security": [
        "maritime", "shipping lane", "vessel seized", "tanker",
        "chokepoint", "strait", "naval blockade", "piracy", "ais",
        "houthi", "bab el-mandeb",
    ],
}


def _keyword_classify(text: str) -> Optional[Dict[str, Any]]:
    """Deterministic keyword-based geopolitical classification. Returns best match or None."""
    lower = text.lower()
    scores: Dict[str, int] = {}
    for cat, keywords in _KEYWORD_RULES.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            scores[cat] = hits
    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    total_kw = sum(len(v) for v in _KEYWORD_RULES.values())
    confidence = min(0.95, 0.4 + scores[best] * 0.15)
    return {"category": best, "confidence": round(confidence, 3)}


async def classify(text: str) -> Optional[Dict[str, Any]]:
    """
    Geopolitical classification — keyword matching first, Haiku fallback for ambiguous cases.
    Returns {"category": str, "confidence": float} or None.
    """
    global _run_classify_count
    if not text or not text.strip():
        return None

    # ── Keyword primary path (free, deterministic — no counter bump) ──
    kw_result = _keyword_classify(text)
    if kw_result and kw_result["confidence"] >= 0.55:
        return kw_result

    # ── Haiku fallback for ambiguous texts ──
    if _run_haiku_failed:
        return kw_result
    if _run_classify_count >= HAIKU_MAX_CLASSIFY_PER_RUN:
        logger.debug("[haiku] Classify limit reached (%d)", HAIKU_MAX_CLASSIFY_PER_RUN)
        return kw_result

    raw = await _call_haiku(_CLASSIFY_SYSTEM, text.strip()[:2000], max_tokens=128, usage_agent="news")
    if not raw:
        return kw_result
    try:
        parsed = json.loads(_strip_json_block(raw))
        _run_classify_count += 1
        category = parsed.get("category", "other")
        if category not in _GEOPOLITICAL_CATEGORIES:
            category = "other"
        return {
            "category": category,
            "confidence": float(parsed.get("confidence", 0)),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("[haiku] Classify response not valid JSON: %.100s", raw)
        return kw_result


async def batch_classify(texts: List[str]) -> List[Optional[Dict[str, Any]]]:
    """Run classification on multiple texts with batch-fallback."""
    results: List[Optional[Dict[str, Any]]] = []
    for t in texts:
        if _run_haiku_failed:
            results.append(None)
            continue
        r = await classify(t)
        results.append(r)
    return results


# ── DIPLO classification (UN/ICJ news) ──────────────────────────────────────

_DIPLO_CATEGORIES = [
    "new_sanction",
    "sanction_lifted",
    "icj_ruling",
    "procedural_update",
    "irrelevant",
]

_CLASSIFY_DIPLO_SYSTEM = (
    "You are a diplomatic/legal news classifier. Classify the following UN or ICJ press text "
    "into exactly ONE of these categories:\n" + ", ".join(_DIPLO_CATEGORIES) + "\n\n"
    "new_sanction = new sanctions, designations, or enforcement actions. "
    "sanction_lifted = removal or easing of sanctions. "
    "icj_ruling = ICJ judgment, order, or substantive ruling. "
    "procedural_update = procedural step, hearing date, filing, or case update. "
    "irrelevant = not about sanctions or ICJ, or not conflict-relevant.\n\n"
    "Return ONLY valid JSON:\n"
    '{"category": "<category>", "confidence": <float 0 to 1>}'
)


async def classify_diplo(text: str) -> Optional[Dict[str, Any]]:
    """
    Classify UN/ICJ news item for DIPLO agent.
    Returns {"category": str, "confidence": float} or None.
    Uses same run limit as classify() (_run_classify_count).
    """
    global _run_classify_count
    if not text or not text.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_classify_count >= HAIKU_MAX_CLASSIFY_PER_RUN:
        logger.debug("[haiku] Classify limit reached (%d)", HAIKU_MAX_CLASSIFY_PER_RUN)
        return None

    raw = await _call_haiku(_CLASSIFY_DIPLO_SYSTEM, text.strip()[:2000], max_tokens=128, usage_agent="diplo")
    if not raw:
        return None
    try:
        parsed = json.loads(_strip_json_block(raw))
        _run_classify_count += 1
        category = parsed.get("category", "irrelevant")
        if category not in _DIPLO_CATEGORIES:
            category = "irrelevant"
        return {
            "category": category,
            "confidence": float(parsed.get("confidence", 0)),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("[haiku] Classify diplo response not valid JSON: %.100s", raw)
        return None


async def batch_classify_diplo(texts: List[str]) -> List[Optional[Dict[str, Any]]]:
    """Run DIPLO classification on multiple texts with batch-fallback."""
    results: List[Optional[Dict[str, Any]]] = []
    for t in texts:
        if _run_haiku_failed:
            results.append(None)
            continue
        r = await classify_diplo(t)
        results.append(r)
    return results


# ── Summarization (Phase 3) ─────────────────────────────────────────────────

_SUMMARIZE_SYSTEM = (
    "You are a geopolitical intelligence summarizer. Condense the following text "
    "into a concise summary (2-4 sentences) that preserves: key actors, actions, "
    "locations, and escalation/de-escalation signals. Maintain factual accuracy. "
    "If the text is in a non-English language, summarize in English.\n\n"
    "Return ONLY the summary text, no JSON, no markdown."
)


async def summarize(text: str, max_output_tokens: int = 256) -> Optional[str]:
    """
    Geopolitically focused summarization.
    Returns the summary string or None.
    """
    global _run_summarize_count
    if not text or not text.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_summarize_count >= HAIKU_MAX_SUMMARIZE_PER_RUN:
        logger.debug("[haiku] Summarize limit reached (%d)", HAIKU_MAX_SUMMARIZE_PER_RUN)
        return None

    result = await _call_haiku(_SUMMARIZE_SYSTEM, text.strip()[:4000], max_tokens=max_output_tokens, usage_agent="news")
    if result:
        _run_summarize_count += 1
    return result


async def batch_summarize(texts: List[str]) -> List[Optional[str]]:
    """Summarize multiple texts with batch-fallback."""
    results: List[Optional[str]] = []
    for t in texts:
        if _run_haiku_failed:
            results.append(None)
            continue
        r = await summarize(t)
        results.append(r)
    return results


# ── Analyst summary (custom system prompt) ───────────────────────────────────


async def analyst_summary(
    system: str,
    data: str,
    max_tokens: int = 256,
    *,
    usage_agent: str = "analyst",
    model: Optional[str] = None,
    skip_run_limits: bool = False,
) -> Optional[str]:
    """
    Generic analyst-style summary with custom system prompt. Use for GreyNoise, TECHINT,
    CYBER, ENERGY, IAEA, etc. Budget-tracked; separate limit from content summarization.
    Optional ``model`` overrides ``HAIKU_MODEL`` for this call.
    When ``skip_run_limits`` is True the per-run analyst counter and the
    ``_run_haiku_failed`` flag are bypassed (used by the chat endpoint so it is
    not blocked by a concurrent or previous analysis run).  Monthly budget and
    global call-count limits still apply.
    """
    global _run_analyst_summary_count
    if not data or not data.strip():
        return None
    if not skip_run_limits:
        if _run_haiku_failed:
            return None
        if _run_analyst_summary_count >= HAIKU_MAX_ANALYST_SUMMARY_PER_RUN:
            logger.debug("[haiku] Analyst summary limit reached (%d)", HAIKU_MAX_ANALYST_SUMMARY_PER_RUN)
            return None

    result = await _call_haiku(
        system.strip(),
        data.strip()[:8000],
        max_tokens=max_tokens,
        usage_agent=usage_agent,
        model=model,
        bypass_per_run_call_limit=skip_run_limits,
    )
    if result:
        _run_analyst_summary_count += 1
    return result


# ── Document QA (Phase 4) ───────────────────────────────────────────────────

_DOCQA_SYSTEM = (
    "You are a geopolitical document analyst. Answer the question based ONLY on the "
    "provided document chunks. If the answer cannot be found in the chunks, say "
    '"I cannot find this information in the provided documents."\n\n'
    "Be precise and cite specific details from the text. If the question is about "
    "a sanctioned entity, include the entity's program, type, and any identifiers.\n\n"
    "Return ONLY valid JSON:\n"
    '{"answer": "<answer text>", "confidence": <float 0 to 1>, '
    '"sources": ["<brief chunk reference>"]}'
)


async def document_qa(
    question: str,
    chunks: List[str],
    max_chunks: int = 5,
) -> Optional[Dict[str, Any]]:
    """
    Answer a question using Haiku over the provided document chunks.
    Returns {"answer", "confidence", "sources"} or None.
    """
    global _run_docqa_count
    if not question or not chunks:
        return None
    if _run_haiku_failed:
        return None
    if _run_docqa_count >= HAIKU_MAX_DOCQA_PER_RUN:
        logger.debug("[haiku] DocQA limit reached (%d)", HAIKU_MAX_DOCQA_PER_RUN)
        return None

    selected = chunks[:max_chunks]
    context_parts = [f"[Chunk {i + 1}]\n{c}" for i, c in enumerate(selected)]
    user_content = "DOCUMENT CHUNKS:\n\n" + "\n\n".join(context_parts) + f"\n\nQUESTION: {question}"

    raw = await _call_haiku(_DOCQA_SYSTEM, user_content[:8000], max_tokens=512, usage_agent="compliance")
    if not raw:
        return None
    try:
        parsed = json.loads(_strip_json_block(raw))
        _run_docqa_count += 1
        return {
            "answer": parsed.get("answer", ""),
            "confidence": float(parsed.get("confidence", 0)),
            "sources": parsed.get("sources", []),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        _run_docqa_count += 1
        return {
            "answer": raw.strip(),
            "confidence": 0.5,
            "sources": [],
        }
