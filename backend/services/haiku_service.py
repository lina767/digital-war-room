"""
Haiku Service — Central wrapper for Claude Haiku 4.5 calls.

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


def _increment_usage(input_tokens: int, output_tokens: int):
    """Track real token usage from the API response."""
    global _monthly_input_tokens, _monthly_output_tokens, _monthly_cost_usd
    global _run_call_count, _run_input_tokens, _run_output_tokens
    _ensure_month()
    _monthly_input_tokens += input_tokens
    _monthly_output_tokens += output_tokens
    cost = (input_tokens / 1_000_000) * _INPUT_COST_PER_MTOK + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_MTOK
    _monthly_cost_usd += cost
    _run_call_count += 1
    _run_input_tokens += input_tokens
    _run_output_tokens += output_tokens

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
    global _run_input_tokens, _run_output_tokens, _run_haiku_failed
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
    _run_haiku_failed = False


def is_haiku_failed() -> bool:
    """True if Haiku encountered an error during this run (batch-fallback signal)."""
    return _run_haiku_failed


def log_run_stats():
    """Log summary at the end of each run."""
    _ensure_month()
    run_cost = (_run_input_tokens / 1_000_000) * _INPUT_COST_PER_MTOK + (
        _run_output_tokens / 1_000_000
    ) * _OUTPUT_COST_PER_MTOK
    logger.info(
        "[haiku] Run stats: %d calls, %d input tokens, %d output tokens, ~$%.4f. Month total: ~$%.2f / $%.2f",
        _run_call_count,
        _run_input_tokens,
        _run_output_tokens,
        run_cost,
        _monthly_cost_usd,
        HAIKU_MONTHLY_BUDGET,
    )


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


async def _call_haiku(system: str, user_content: str, max_tokens: int = 1024) -> Optional[str]:
    """
    Low-level Haiku call with budget/limit checks and usage tracking.
    Returns the text response or None on any failure.
    """
    if _run_call_count >= HAIKU_MAX_CALLS_PER_RUN:
        logger.warning("[haiku] Run call limit reached (%d)", HAIKU_MAX_CALLS_PER_RUN)
        return None
    if not _check_budget():
        logger.warning("[haiku] Monthly budget exhausted")
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import asyncio

        loop = asyncio.get_running_loop()
        client = _get_client()
        resp = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=HAIKU_MODEL,
                system=system,
                messages=[{"role": "user", "content": user_content}],
                temperature=0,
                max_tokens=max_tokens,
            ),
        )
        _increment_usage(
            resp.usage.input_tokens,
            resp.usage.output_tokens,
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

    result = await _call_haiku(_TRANSLATE_SYSTEM, text.strip(), max_tokens=2048)
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
    Multilingual sentiment analysis on original text.
    Returns {"label", "score", "confidence", "reasoning"} or None.
    """
    global _run_sentiment_count
    if not text or not text.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_sentiment_count >= HAIKU_MAX_SENTIMENT_PER_RUN:
        logger.debug("[haiku] Sentiment limit reached (%d)", HAIKU_MAX_SENTIMENT_PER_RUN)
        return None

    raw = await _call_haiku(_SENTIMENT_SYSTEM, text.strip()[:2000], max_tokens=256)
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


async def ner(text: str) -> Optional[List[Dict[str, str]]]:
    """
    Domain-specific Named Entity Recognition.
    Returns [{"entity", "type", "context"}] or None.
    """
    global _run_ner_count
    if not text or not text.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_ner_count >= HAIKU_MAX_NER_PER_RUN:
        logger.debug("[haiku] NER limit reached (%d)", HAIKU_MAX_NER_PER_RUN)
        return None

    raw = await _call_haiku(_NER_SYSTEM, text.strip()[:3000], max_tokens=1024)
    if not raw:
        return None
    try:
        parsed = json.loads(_strip_json_block(raw))
        if isinstance(parsed, list):
            _run_ner_count += 1
            return [
                {
                    "entity": e.get("entity", ""),
                    "type": e.get("type", "MISC"),
                    "context": e.get("context", ""),
                }
                for e in parsed
                if isinstance(e, dict) and e.get("entity")
            ]
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("[haiku] NER response not valid JSON: %.100s", raw)
    return None


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
    "protest_civil_unrest",
    "maritime_security",
    "other",
]

_CLASSIFY_SYSTEM = (
    "You are a geopolitical intelligence classifier. Classify the following text "
    "into exactly ONE of these categories:\n" + ", ".join(_GEOPOLITICAL_CATEGORIES) + "\n\n"
    "Return ONLY valid JSON:\n"
    '{"category": "<category>", "confidence": <float 0 to 1>}'
)


async def classify(text: str) -> Optional[Dict[str, Any]]:
    """
    Zero-shot geopolitical classification.
    Returns {"category": str, "confidence": float} or None.
    """
    global _run_classify_count
    if not text or not text.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_classify_count >= HAIKU_MAX_CLASSIFY_PER_RUN:
        logger.debug("[haiku] Classify limit reached (%d)", HAIKU_MAX_CLASSIFY_PER_RUN)
        return None

    raw = await _call_haiku(_CLASSIFY_SYSTEM, text.strip()[:2000], max_tokens=128)
    if not raw:
        return None
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
        return None


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

    raw = await _call_haiku(_CLASSIFY_DIPLO_SYSTEM, text.strip()[:2000], max_tokens=128)
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

    result = await _call_haiku(_SUMMARIZE_SYSTEM, text.strip()[:4000], max_tokens=max_output_tokens)
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
) -> Optional[str]:
    """
    Generic analyst-style summary with custom system prompt. Use for GreyNoise, TECHINT,
    CYBER, ENERGY, IAEA, etc. Budget-tracked; separate limit from content summarization.
    """
    global _run_analyst_summary_count
    if not data or not data.strip():
        return None
    if _run_haiku_failed:
        return None
    if _run_analyst_summary_count >= HAIKU_MAX_ANALYST_SUMMARY_PER_RUN:
        logger.debug("[haiku] Analyst summary limit reached (%d)", HAIKU_MAX_ANALYST_SUMMARY_PER_RUN)
        return None

    result = await _call_haiku(system.strip(), data.strip()[:8000], max_tokens=max_tokens)
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

    raw = await _call_haiku(_DOCQA_SYSTEM, user_content[:8000], max_tokens=512)
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
