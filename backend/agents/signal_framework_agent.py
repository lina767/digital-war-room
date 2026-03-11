"""
Signal Framework (Narrative Comparison) Agent – State vs Exile/Independent Media.

Compares two camps of sources for conflict coverage (e.g. Iran):
- State: IRNA, Fars News, Tasnim, Press TV
- Exile/Independent: Iran International, Radio Farda, BBC Persian, X/Telegram via aggregators

Analyzes four signals: Lexical, Latency, Discrepancy, Reaction.
Output: Source comparison table, signal assessment, synthesis (Bayesian-style), anomalies.
All output in English for frontend.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import feedparser
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Source groups (Iran narrative comparison) ────────────────────────────────

STATE_SOURCES: List[Dict[str, str]] = [
    {"name": "IRNA", "url": "https://www.irna.ir/en/rss.aspx?kind=-1"},
    {"name": "Fars News", "url": "https://www.farsnews.ir/en/rss"},  # fallback: https://www.farsnews.com/rss/politics
    {"name": "Tasnim", "url": "https://www.tasnimnews.ir/en/rss"},
    {"name": "Press TV", "url": "https://www.presstv.ir/rss/world.xml"},
]

EXILE_SOURCES: List[Dict[str, str]] = [
    {"name": "Iran International", "url": "https://iranintl.com/en/rss"},
    {"name": "Radio Farda", "url": "https://www.radiofarda.com/api/zkqopekqqop_ztql"},  # RFE/RL Farda feed
    {"name": "BBC Persian", "url": "https://www.bbc.com/persian/index.xml"},
]

# Lexical framing: terms often used by state vs exile (for comparison hints)
STATE_FRAMING_TERMS = [
    "rioter", "sedition", "conspiracy", "enemy", "terrorist", "sabotage",
    "hypocrite", "arrest", "restore order", "foreign-backed",
]
EXILE_FRAMING_TERMS = [
    "protester", "protest", "demonstration", "crackdown", "killed", "detained",
    "human rights", "abuse", "regime", "supreme leader",
]
REACTION_KEYWORDS = ["deny", "denial", "dismiss", "reject", "accusation", "conspiracy", "fake", "fabricated"]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_feed_item_published(entry: Any) -> Optional[float]:
    """Return Unix timestamp for feed entry published/updated time, or None."""
    try:
        published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if published:
            from time import mktime
            return mktime(published)
        raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
        if raw and isinstance(raw, str):
            from dateutil import parser as date_parser
            dt = date_parser.parse(raw)
            return dt.timestamp()
    except Exception:
        pass
    return None


def _fetch_feed(url: str, source_name: str) -> List[Dict[str, Any]]:
    """Fetch single RSS feed and return list of items with title, link, published_ts, source_name, text."""
    items: List[Dict[str, Any]] = []
    try:
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; SignalFramework/1.0)"},
        )
        for entry in getattr(parsed, "entries", [])[:25]:
            title = (getattr(entry, "title", None) or "").strip()
            link = getattr(entry, "link", None) or ""
            summary = (getattr(entry, "summary", None) or getattr(entry, "description", None) or "").strip()
            if not title and not link:
                continue
            ts = _parse_feed_item_published(entry)
            text = f"{title} {summary}"
            items.append({
                "title": title[:500],
                "link": link,
                "published_ts": ts,
                "source_name": source_name,
                "text": text[:2000],
            })
    except Exception as e:
        logger.debug("SignalFramework: feed %s failed: %s", url[:50], e)
    return items


def _tokenize_for_lexical(text: str) -> List[str]:
    """Simple word tokenization for lexical comparison (ASCII + Unicode letters, lowercased)."""
    if not text:
        return []
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    words = normalized.split()
    stop = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "is", "are", "was", "were", "be", "been", "by", "with", "from", "as", "this", "that"}
    return [w for w in words if len(w) > 2 and w not in stop]


def _extract_key_terms(items: List[Dict[str, Any]], top_n: int = 12) -> List[str]:
    """Extract most frequent meaningful terms from camp items."""
    from collections import Counter
    all_tokens: List[str] = []
    for it in items:
        all_tokens.extend(_tokenize_for_lexical(it.get("text") or it.get("title") or ""))
    counts = Counter(all_tokens)
    return [w for w, _ in counts.most_common(top_n)]


def _first_mention_ts(items: List[Dict[str, Any]]) -> Optional[float]:
    """Earliest published_ts in list (for latency signal)."""
    timestamps = [it["published_ts"] for it in items if it.get("published_ts") is not None]
    return min(timestamps) if timestamps else None


def _detect_reaction_signals(state_items: List[Dict[str, Any]]) -> List[str]:
    """Heuristic: phrases suggesting defensive reaction (denial, deflection)."""
    signals: List[str] = []
    for it in state_items:
        text = (it.get("text") or it.get("title") or "").lower()
        for kw in REACTION_KEYWORDS:
            if kw in text:
                signals.append(f"State media uses '{kw}' in: {it.get('title', '')[:80]}...")
                break
    return signals[:5]


def _synthesis_confidence(
    state_items: List[Dict[str, Any]],
    exile_items: List[Dict[str, Any]],
    latency_hours: Optional[float],
    reaction_signals: List[str],
) -> Tuple[float, str]:
    """
    Simple Bayesian-style confidence: probability that event reporting is consistent.
    Returns (0-1 score, short synthesis text).
    """
    score = 0.5
    if state_items and exile_items:
        score += 0.15
    if latency_hours is not None:
        if latency_hours > 24:
            score -= 0.2  # large information vacuum suggests opacity
        elif latency_hours < 2:
            score += 0.1  # both sides reported quickly
    if reaction_signals:
        score -= 0.1 * min(len(reaction_signals), 3)
    score = max(0.0, min(1.0, score))
    if score >= 0.7:
        synth = "High consistency across state and exile sources; narrative convergence supports a single coherent event interpretation."
    elif score >= 0.5:
        synth = "Moderate consistency; some divergence in framing and timing. Cross-check with visual or social evidence recommended."
    else:
        synth = "Low consistency; significant latency or framing gaps. Likely information vacuum or conflicting narratives—treat as contested."
    return (round(score, 2), synth)


# ── Pydantic output models ───────────────────────────────────────────────────

class SourceComparisonRow(BaseModel):
    point: str
    state_narrative: str
    exile_narrative: str


class SignalAssessment(BaseModel):
    latency: str
    credibility_gaps: str


class SignalSummary(BaseModel):
    """Four signals for frontend display (Methodology: Signal Framework)."""
    lexical: Dict[str, Any] = Field(default_factory=dict)   # state_terms, exile_terms, interpretation hint
    latency: str = ""
    discrepancy: str = ""   # narrative vs visual/social evidence gaps
    reaction: List[str] = Field(default_factory=list)      # defensive/denial/deflection signals


class SignalFrameworkReport(BaseModel):
    conflict: str
    source_comparison_table: List[SourceComparisonRow] = Field(default_factory=list)
    signal_assessment: SignalAssessment = Field(default_factory=lambda: SignalAssessment(latency="", credibility_gaps=""))
    signals: Optional[SignalSummary] = None   # explicit 4-signal breakdown for UI
    synthesis_probability: float = 0.0
    synthesis_text: str = ""
    anomalies: List[str] = Field(default_factory=list)
    lexical_state_terms: List[str] = Field(default_factory=list)
    lexical_exile_terms: List[str] = Field(default_factory=list)
    reaction_signals: List[str] = Field(default_factory=list)
    state_item_count: int = 0
    exile_item_count: int = 0
    fetched_at: str = Field(default_factory=_utc_iso)
    error: Optional[str] = None


def run_signal_framework_agent(conflict: str) -> Dict[str, Any]:
    """
    Run the Signal Framework: compare state vs exile/independent sources,
    compute lexical, latency, discrepancy, and reaction signals; return structured report in English.
    """
    cl = (conflict or "").lower()
    if "iran" not in cl:
        return SignalFrameworkReport(
            conflict=conflict,
            synthesis_text="Signal Framework is configured for Iran narrative comparison. No analysis run.",
            error="conflict_not_supported",
        ).model_dump(mode="json")

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            state_futures = [executor.submit(_fetch_feed, s["url"], s["name"]) for s in STATE_SOURCES]
            exile_futures = [executor.submit(_fetch_feed, s["url"], s["name"]) for s in EXILE_SOURCES]

            state_items: List[Dict[str, Any]] = []
            for fut in state_futures:
                try:
                    state_items.extend(fut.result(timeout=20) or [])
                except Exception as e:
                    logger.debug("SignalFramework: state feed failed: %s", e)

            exile_items: List[Dict[str, Any]] = []
            for fut in exile_futures:
                try:
                    exile_items.extend(fut.result(timeout=20) or [])
                except Exception as e:
                    logger.debug("SignalFramework: exile feed failed: %s", e)

        # Lexical signal
        state_terms = _extract_key_terms(state_items)
        exile_terms = _extract_key_terms(exile_items)
        state_framing = [t for t in state_terms if t in STATE_FRAMING_TERMS or any(t in ft for ft in STATE_FRAMING_TERMS)]
        exile_framing = [t for t in exile_terms if t in EXILE_FRAMING_TERMS or any(t in ft for ft in EXILE_FRAMING_TERMS)]

        main_state = state_items[0].get("title", "") if state_items else ""
        main_exile = exile_items[0].get("title", "") if exile_items else ""

        table = [
            SourceComparisonRow(
                point="Main claim",
                state_narrative=main_state[:400] if main_state else "No state coverage retrieved.",
                exile_narrative=main_exile[:400] if main_exile else "No exile/independent coverage retrieved.",
            ),
            SourceComparisonRow(
                point="Key terms",
                state_narrative=", ".join(state_terms[:15]) if state_terms else "—",
                exile_narrative=", ".join(exile_terms[:15]) if exile_terms else "—",
            ),
        ]

        # Latency signal
        ts_state = _first_mention_ts(state_items)
        ts_exile = _first_mention_ts(exile_items)
        latency_str = "Not enough timestamps to compare."
        latency_hours: Optional[float] = None
        if ts_state is not None and ts_exile is not None:
            diff_sec = abs(ts_state - ts_exile)
            latency_hours = diff_sec / 3600.0
            if ts_state < ts_exile:
                latency_str = f"State media reported first (≈{latency_hours:.1f}h before exile sources)."
            else:
                latency_str = f"Exile/independent media reported first (≈{latency_hours:.1f}h before state). Information vacuum on state side possible."
        elif ts_state is None and state_items:
            latency_str = "State sources: publication times missing or unparseable."
        elif ts_exile is None and exile_items:
            latency_str = "Exile sources: publication times missing or unparseable."

        # Reaction signal
        reaction_signals = _detect_reaction_signals(state_items)
        discrepancy_note = "No automated discrepancy check; compare narratives with social/media imagery manually."
        credibility_gaps = discrepancy_note
        if reaction_signals:
            credibility_gaps = "State framing shows defensive or denial language. " + discrepancy_note

        # Synthesis
        prob, synth_text = _synthesis_confidence(state_items, exile_items, latency_hours, reaction_signals)

        # Anomalies: logical but unmentioned (placeholder)
        anomalies: List[str] = []
        if not state_items and not exile_items:
            anomalies.append("No items from either camp—check feed availability or filters.")
        elif state_items and not exile_items:
            anomalies.append("Only state-side coverage available; exile/independent feeds may be blocked or down.")
        elif exile_items and not state_items:
            anomalies.append("Only exile-side coverage available; state feeds may be restricted.")

        signals = SignalSummary(
            lexical={
                "state_terms": state_terms[:15],
                "exile_terms": exile_terms[:15],
                "interpretation": "Compare terms: state framing (e.g. rioter/sedition) vs exile framing (e.g. protester/crackdown) reveals narrative intent.",
            },
            latency=latency_str,
            discrepancy=credibility_gaps,
            reaction=reaction_signals,
        )

        report = SignalFrameworkReport(
            conflict=conflict,
            source_comparison_table=[t.model_dump() for t in table],
            signal_assessment=SignalAssessment(latency=latency_str, credibility_gaps=credibility_gaps),
            signals=signals,
            synthesis_probability=prob,
            synthesis_text=synth_text,
            anomalies=anomalies,
            lexical_state_terms=state_terms[:15],
            lexical_exile_terms=exile_terms[:15],
            reaction_signals=reaction_signals,
            state_item_count=len(state_items),
            exile_item_count=len(exile_items),
        )
        return report.model_dump(mode="json")
    except Exception as e:
        logger.exception("SignalFramework: run failed for conflict '%s': %s", conflict, e)
        return SignalFrameworkReport(
            conflict=conflict,
            error=str(e),
            synthesis_text="Signal Framework analysis failed.",
        ).model_dump(mode="json")
