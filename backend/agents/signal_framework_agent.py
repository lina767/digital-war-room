"""
Signal Framework (Narrative Comparison) Agent – State vs Exile/Independent Media.

Compares two camps of sources for conflict coverage (e.g. Iran):
- State: IRNA, Fars News, Tasnim, Press TV
- Exile/Independent: Iran International, Radio Farda, BBC Persian, X/Telegram via aggregators

Analyzes four signals: Lexical, Latency, Discrepancy, Reaction.
Output: Source comparison table, signal assessment, synthesis (Bayesian-style), anomalies.
All output in English for frontend.
"""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from pydantic import BaseModel, Field

from .health_registry import get_health_registry
from .utils import SourceResult, utc_now_iso

logger = logging.getLogger(__name__)

# Exile source that provides English content (prioritized for display)
ENGLISH_EXILE_SOURCE = "Iran International"
FEED_REQUEST_TIMEOUT = 18
# State feeds: longer timeout and optional retry; Firecrawl fallback when direct fetch fails
FEED_REQUEST_TIMEOUT_STATE = int(os.getenv("SIGNAL_FRAMEWORK_STATE_TIMEOUT", "25"))
SIGNAL_FRAMEWORK_USE_FIRECRAWL = os.getenv("SIGNAL_FRAMEWORK_USE_FIRECRAWL", "").strip().lower() in ("1", "true", "yes")
SIGNAL_FRAMEWORK_GEMINI_DEEP_ANALYSIS = os.getenv("SIGNAL_FRAMEWORK_GEMINI_DEEP_ANALYSIS", "true").strip().lower() in ("1", "true", "yes")
SIGNAL_FRAMEWORK_GEMINI_MAX_ITEMS = max(6, min(40, int(os.getenv("SIGNAL_FRAMEWORK_GEMINI_MAX_ITEMS", "18"))))
SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES = max(3, min(20, int(os.getenv("SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES", "8"))))

# ── Source groups (theater-dependent narrative comparison) ───────────────────

SOURCE_PROFILES: Dict[str, Dict[str, Any]] = {
    "iran": {
        "camp_a_label": "State / Official",
        "camp_b_label": "Exile / Independent",
        "english_camp_b_source": "Iran International",
        "camp_a_sources": [
            {"name": "IRNA", "url": "https://www.irna.ir/en/rss.aspx?kind=-1", "allowed_domains": ["irna.ir"]},
            {"name": "Fars News", "url": "https://www.farsnews.ir/en/rss", "allowed_domains": ["farsnews.ir"]},
            {"name": "Fars News (alt)", "url": "https://www.farsnews.ir/en", "allowed_domains": ["farsnews.ir"]},  # fallback when RSS is blocked/unavailable
            {"name": "Tasnim", "url": "https://www.tasnimnews.ir/en/rss", "allowed_domains": ["tasnimnews.com", "tasnimnews.ir"]},
            {"name": "Press TV", "url": "https://www.presstv.ir/", "allowed_domains": ["presstv.ir"]},
        ],
        "camp_b_sources": [
            {"name": "Iran International", "url": "https://www.iranintl.com/en", "allowed_domains": ["iranintl.com"]},
            {"name": "Radio Farda", "url": "https://www.radiofarda.com/", "allowed_domains": ["radiofarda.com", "rferl.org"]},
            {"name": "BBC Persian", "url": "https://www.bbc.com/persian/index.xml", "allowed_domains": ["bbc.com", "bbci.co.uk"]},
        ],
    },
    "lebanon": {
        "camp_a_label": "Official / Aligned",
        "camp_b_label": "Counter / Independent",
        "english_camp_b_source": "L'Orient Today",
        "camp_a_sources": [
            {"name": "IDF", "url": "https://www.idf.il/en/", "allowed_domains": ["idf.il"]},
            {"name": "Israel MFA", "url": "https://www.gov.il/en/pages/mfa-news-and-articles", "allowed_domains": ["gov.il"]},
            {"name": "Al-Manar", "url": "https://english.almanar.com.lb/", "allowed_domains": ["almanar.com.lb"]},
        ],
        "camp_b_sources": [
            {"name": "L'Orient Today", "url": "https://today.lorientlejour.com/rss", "allowed_domains": ["lorientlejour.com"]},
            {"name": "The New Arab", "url": "https://www.newarab.com/rss.xml", "allowed_domains": ["newarab.com"]},
            {"name": "Middle East Eye", "url": "https://www.middleeasteye.net/rss", "allowed_domains": ["middleeasteye.net"]},
        ],
    },
}


def _source_profile_for_conflict(conflict: str) -> Optional[Dict[str, Any]]:
    cl = (conflict or "").strip().lower()
    if "iran" in cl:
        return SOURCE_PROFILES["iran"]
    if "lebanon" in cl or "hezbollah" in cl:
        return SOURCE_PROFILES["lebanon"]
    if "middle east" in cl:
        return SOURCE_PROFILES["lebanon"]
    return None

# Lexical framing: terms often used by state vs exile (for comparison hints)
STATE_FRAMING_TERMS = [
    "rioter",
    "sedition",
    "conspiracy",
    "enemy",
    "terrorist",
    "sabotage",
    "hypocrite",
    "arrest",
    "restore order",
    "foreign-backed",
]
EXILE_FRAMING_TERMS = [
    "demonstrator",
    "demonstration",
    "demonstration",
    "crackdown",
    "killed",
    "detained",
    "human rights",
    "abuse",
    "regime",
    "supreme leader",
]
REACTION_KEYWORDS = ["deny", "denial", "dismiss", "reject", "accusation", "conspiracy", "fake", "fabricated"]

# War/conflict relevance prioritization to avoid culture-heavy state narratives.
WAR_KEYWORDS = [
    "war",
    "attack",
    "airstrike",
    "missile",
    "rocket",
    "drone",
    "military",
    "army",
    "navy",
    "air force",
    "troops",
    "frontline",
    "offensive",
    "defensive",
    "ceasefire",
    "hostage",
    "detained",
    "killed",
    "wounded",
    "casualties",
    "artillery",
    "bomb",
    "explosion",
    "border clash",
    "idf",
    "irgc",
    "hezbollah",
    "hamas",
]
NON_WAR_CULTURE_KEYWORDS = [
    "culture",
    "cinema",
    "film",
    "festival",
    "music",
    "art exhibition",
    "sports",
    "football",
    "volleyball",
    "tourism",
    "heritage",
]


def _is_mostly_farsi(text: str) -> bool:
    """True if text is predominantly in Persian/Arabic script (U+0600–U+06FF)."""
    if not text or not text.strip():
        return False
    chars = [c for c in text if c.strip()]
    if not chars:
        return False
    farsi_count = sum(1 for c in chars if "\u0600" <= c <= "\u06ff")
    return farsi_count / len(chars) >= 0.3


def _ensure_english_display(
    state_val: Optional[str], exile_val: Optional[str], exile_en_val: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """
    For display we want English. If exile content is Farsi and no English version,
    attempt Haiku translation; fall back to placeholder on failure.
    Returns (state_en_display, exile_en_display).
    """
    state_en = (state_val or "").strip() or None
    exile_en = (exile_en_val or "").strip() or None
    exile_raw = (exile_val or "").strip()
    if exile_raw and _is_mostly_farsi(exile_raw) and (not exile_en or _is_mostly_farsi(exile_en)):
        try:
            from agents.utils import run_async
            from services.haiku_service import translate_fa_en

            translated = run_async(translate_fa_en(exile_raw))
            if translated:
                exile_en = translated
            else:
                exile_en = "Content in Farsi (no English translation in this run)."
        except Exception:
            exile_en = "Content in Farsi (no English translation in this run)."
    elif not exile_en and exile_raw and not _is_mostly_farsi(exile_raw):
        exile_en = exile_raw
    elif not exile_en and exile_raw:
        try:
            from agents.utils import run_async
            from services.haiku_service import translate_fa_en

            translated = run_async(translate_fa_en(exile_raw))
            if translated:
                exile_en = translated
            else:
                exile_en = "Content in Farsi (no English translation in this run)."
        except Exception:
            exile_en = "Content in Farsi (no English translation in this run)."
    return state_en or None, exile_en or None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_feed_item_published(entry: Any) -> Optional[float]:
    """Return Unix timestamp for feed entry; try published_parsed, updated_parsed, dc/dcterms, then raw date strings."""
    try:
        for attr in ("published_parsed", "updated_parsed", "created_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                return time.mktime(parsed)
        for key in ("dc_date", "dcterms_modified", "published", "updated", "created"):
            raw = getattr(entry, key, None) or (entry.get(key) if isinstance(entry, dict) else None)
            if raw and isinstance(raw, str):
                from dateutil import parser as date_parser

                dt = date_parser.parse(raw)
                return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def _fetch_via_firecrawl(url: str, source_name: str) -> List[Dict[str, Any]]:
    """
    Fallback for state feeds: scrape URL via Firecrawl and extract headline-like lines from markdown.
    Returns list of items with title, link (if found), source_name, published_ts (now), text.
    """
    items: List[Dict[str, Any]] = []
    fallback_ts = time.time()
    try:
        from firecrawl import Firecrawl

        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            return items
        app = Firecrawl(api_key=api_key)
        result = app.scrape(url, formats=["markdown"])
        if not result:
            return items
        if isinstance(result, dict) and not result.get("success", True):
            return items
        data = (result or {}).get("data", result) if isinstance(result, dict) else result
        if not isinstance(data, dict):
            data = {"markdown": str(data)} if data else {}
        markdown = (data.get("markdown") or "").strip()
        if not markdown:
            return items
        # Extract lines that look like headlines: 20–400 chars, not just whitespace/symbols
        for line in markdown.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or len(line) < 20 or len(line) > 400:
                continue
            # Remove markdown list prefix and link syntax for display
            title = re.sub(r"^\s*[-*]\s*", "", line)
            title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
            if len(title) < 15:
                continue
            items.append(
                {
                    "title": title[:500],
                    "link": "",
                    "published_ts": fallback_ts,
                    "source_name": source_name,
                    "text": title[:2000],
                }
            )
        if items:
            logger.info(
                "SignalFramework: source %s got %d items via Firecrawl fallback.", source_name, len(items)
            )
    except Exception as e:
        logger.debug("SignalFramework: Firecrawl fallback for %s failed: %s", source_name, e)
    return items[:25]


def _extract_headlines_from_html(html: str, base_url: str, source_name: str) -> List[Dict[str, Any]]:
    """Best-effort fallback: extract headline-like anchor texts from HTML pages."""
    if not html:
        return []
    fallback_ts = time.time()
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    # <a href="...">headline text</a>
    for href, txt in re.findall(r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        text = re.sub(r"<[^>]+>", " ", txt or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 25 or len(text) > 260:
            continue
        href = (href or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        link = urljoin(base_url, href)
        key = f"{text.lower()}|{link}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": text[:500],
                "link": link,
                "published_ts": fallback_ts,
                "source_name": source_name,
                "text": text[:2000],
            }
        )
        if len(out) >= 25:
            break
    return out


def _fetch_feed(url: str, source_name: str, state_source_names: set[str]) -> List[Dict[str, Any]]:
    """Fetch RSS via httpx (timeout, browser UA). On state failure: retry once, then Firecrawl fallback if enabled."""
    items: List[Dict[str, Any]] = []
    fallback_ts = time.time()
    is_state = source_name in state_source_names
    timeout = FEED_REQUEST_TIMEOUT_STATE if is_state else FEED_REQUEST_TIMEOUT
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0"}

    def _do_fetch() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        raw_body = b""
        content_type = ""
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
                r.raise_for_status()
                raw_body = r.content or b""
                content_type = (r.headers.get("content-type") or "").lower()
                parsed = feedparser.parse(raw_body)
        except Exception as e:
            logger.warning("SignalFramework: fetch failed for %s (%s): %s", source_name, url[:50], e)
            return out
        for entry in getattr(parsed, "entries", [])[:25]:
            title = (getattr(entry, "title", None) or "").strip()
            link = getattr(entry, "link", None) or ""
            summary = (getattr(entry, "summary", None) or getattr(entry, "description", None) or "").strip()
            if not title and not link:
                continue
            ts = _parse_feed_item_published(entry)
            if ts is None:
                ts = fallback_ts
            text = f"{title} {summary}"
            out.append(
                {
                    "title": title[:500],
                    "link": link,
                    "published_ts": ts,
                    "source_name": source_name,
                    "text": text[:2000],
                }
            )
        # Fallback: some sources no longer expose RSS and return plain HTML.
        if not out and raw_body:
            try:
                body_text = raw_body.decode("utf-8", errors="replace")
                if "html" in content_type or body_text.lstrip().lower().startswith("<!doctype html"):
                    out = _extract_headlines_from_html(body_text, url, source_name)
            except (UnicodeDecodeError, ValueError, TypeError) as exc:
                logger.debug("SignalFramework: HTML fallback parse failed for %s: %s", source_name, exc)
        return out

    items = _do_fetch()
    # Option 4: one retry for state sources when first attempt returned 0 items (transient timeout/5xx)
    if is_state and not items:
        logger.debug("SignalFramework: retrying state source %s once.", source_name)
        time.sleep(0.5)
        items = _do_fetch()
    if not items and SIGNAL_FRAMEWORK_USE_FIRECRAWL and os.getenv("FIRECRAWL_API_KEY"):
        items = _fetch_via_firecrawl(url, source_name)
    if not items and is_state:
        logger.warning("SignalFramework: state source %s returned 0 items (may be geo-restricted).", source_name)
    return items


def _tokenize_for_lexical(text: str) -> List[str]:
    """Simple word tokenization for lexical comparison (ASCII + Unicode letters, lowercased)."""
    if not text:
        return []
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    words = normalized.split()
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "by",
        "with",
        "from",
        "as",
        "this",
        "that",
    }
    return [w for w in words if len(w) > 2 and w not in stop]


def _extract_key_terms(items: List[Dict[str, Any]], top_n: int = 12) -> List[str]:
    """Extract most frequent meaningful terms from camp items."""
    from collections import Counter

    all_tokens: List[str] = []
    for it in items:
        all_tokens.extend(_tokenize_for_lexical(it.get("text") or it.get("title") or ""))
    counts = Counter(all_tokens)
    return [w for w, _ in counts.most_common(top_n)]


def _war_relevance_score(item: Dict[str, Any]) -> float:
    txt = f"{item.get('title') or ''} {item.get('text') or ''}".lower()
    if not txt.strip():
        return 0.0
    score = 0.0
    for kw in WAR_KEYWORDS:
        if kw in txt:
            score += 1.0
    for kw in NON_WAR_CULTURE_KEYWORDS:
        if kw in txt:
            score -= 0.8
    return score


def _prioritize_war_items(items: List[Dict[str, Any]], max_items: int = 40) -> List[Dict[str, Any]]:
    """
    Prefer war/conflict-relevant rows. If none match, fall back to recency.
    """
    ranked = sorted(items, key=lambda x: (_war_relevance_score(x), x.get("published_ts") or 0), reverse=True)
    war_only = [r for r in ranked if _war_relevance_score(r) > 0]
    if war_only:
        return war_only[:max_items]
    return ranked[:max_items]


def _domain_allowed(link: str, allowed_domains: List[str]) -> bool:
    if not link or not allowed_domains:
        return True
    try:
        host = (urlparse(link).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in [x.lower() for x in allowed_domains if x])


def _apply_source_whitelist(items: List[Dict[str, Any]], allowed_domains: List[str]) -> List[Dict[str, Any]]:
    if not items:
        return []
    if not allowed_domains:
        return items
    out: List[Dict[str, Any]] = []
    for row in items:
        link = str(row.get("link") or "").strip()
        # Scraped headline rows can have no permalink; keep them but only with reduced confidence downstream.
        if not link or _domain_allowed(link, allowed_domains):
            out.append(row)
    return out


_LOSS_WORDS = r"(killed|dead|wounded|injured|casualties|losses)"
_IDF_WORDS = r"(idf|israel(?:i)?(?:\s+army|\s+forces|\s+troops|\s+soldiers?)?)"
_HEZB_WORDS = r"(hezbollah|hizbullah|hezb(?:\s+fighters?)?)"


def _extract_loss_claims(text: str) -> List[Tuple[str, str, int]]:
    """
    Extract (actor, metric, value) tuples from claim text.
    actor in {idf, hezbollah}, metric in {killed,wounded,casualties,losses}.
    """
    if not text:
        return []
    t = text.lower()
    claims: List[Tuple[str, str, int]] = []
    patterns = [
        rf"(\d{{1,4}})\s+{_LOSS_WORDS}\s+(?:among\s+)?{_IDF_WORDS}",
        rf"{_IDF_WORDS}[^.:\n]{{0,45}}?(\d{{1,4}})\s+{_LOSS_WORDS}",
        rf"(\d{{1,4}})\s+{_LOSS_WORDS}\s+(?:among\s+)?{_HEZB_WORDS}",
        rf"{_HEZB_WORDS}[^.:\n]{{0,45}}?(\d{{1,4}})\s+{_LOSS_WORDS}",
    ]
    for idx, pattern in enumerate(patterns):
        for m in re.finditer(pattern, t, flags=re.IGNORECASE):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            num = None
            metric = "casualties"
            actor = "idf" if idx < 2 else "hezbollah"
            for g in groups:
                g_l = str(g).lower()
                if g_l.isdigit():
                    num = int(g_l)
                elif g_l in ("killed", "dead", "wounded", "injured", "casualties", "losses"):
                    metric = "killed" if g_l == "dead" else ("wounded" if g_l == "injured" else g_l)
            if num is not None and 0 <= num <= 5000:
                claims.append((actor, metric, num))
    return claims


def _camp_claim_digest(items: List[Dict[str, Any]]) -> Dict[Tuple[str, str], int]:
    acc: Dict[Tuple[str, str], int] = {}
    for it in items[:20]:
        text = f"{it.get('title') or ''} {it.get('text') or ''}".strip()
        for actor, metric, value in _extract_loss_claims(text):
            key = (actor, metric)
            if key not in acc:
                acc[key] = value
            else:
                # Keep higher claimed value for conservative mismatch detection.
                acc[key] = max(acc[key], value)
    return acc


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
    state_narrative_en: Optional[str] = None  # English; state feeds are usually EN
    exile_narrative_en: Optional[str] = None  # English; from Iran International or translated
    source_reliability_tier: Optional[str] = None
    verification_state: Optional[str] = None


class SignalAssessment(BaseModel):
    latency: str
    credibility_gaps: str


class SignalSummary(BaseModel):
    """Four signals for frontend display (Methodology: Signal Framework)."""

    lexical: Dict[str, Any] = Field(default_factory=dict)  # state_terms, exile_terms, interpretation hint
    latency: str = ""
    discrepancy: str = ""  # narrative vs visual/social evidence gaps
    reaction: List[str] = Field(default_factory=list)  # defensive/denial/deflection signals


class SignalFrameworkReport(BaseModel):
    conflict: str
    source_comparison_table: List[SourceComparisonRow] = Field(default_factory=list)
    signal_assessment: SignalAssessment = Field(
        default_factory=lambda: SignalAssessment(latency="", credibility_gaps="")
    )
    signals: Optional[SignalSummary] = None  # explicit 4-signal breakdown for UI
    synthesis_probability: float = 0.0
    synthesis_text: str = ""
    camp_a_label: str = "State / Official"
    camp_b_label: str = "Exile / Independent"
    source_reliability_tier: Optional[str] = None
    verification_state: Optional[str] = None
    claim_conflicts: List[str] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    lexical_state_terms: List[str] = Field(default_factory=list)
    lexical_exile_terms: List[str] = Field(default_factory=list)
    reaction_signals: List[str] = Field(default_factory=list)
    theme_clusters: List[Dict[str, Any]] = Field(default_factory=list)
    quoted_passages: List[Dict[str, Any]] = Field(default_factory=list)
    negotiation_narrative_score: Optional[float] = None
    method_notes: List[str] = Field(default_factory=list)
    state_item_count: int = 0
    exile_item_count: int = 0
    fetched_at: str = Field(default_factory=_utc_iso)
    error: Optional[str] = None


def _prepare_gemini_items(state_items: List[Dict[str, Any]], exile_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined = sorted(
        [*state_items, *exile_items],
        key=lambda x: -(x.get("published_ts") or 0),
    )
    out: List[Dict[str, Any]] = []
    for row in combined[:SIGNAL_FRAMEWORK_GEMINI_MAX_ITEMS]:
        title = str(row.get("title") or "").strip()
        text = str(row.get("text") or "").strip()
        source = str(row.get("source_name") or "").strip()
        if not title and not text:
            continue
        out.append(
            {
                "source_name": source[:120] or "unknown",
                "title": title[:500],
                "snippet": text[:1200],
                "published_ts": row.get("published_ts"),
                "link": str(row.get("link") or "")[:500],
            }
        )
    return out


def _build_gemini_prompt(conflict: str, items: List[Dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False)
    return (
        "You are an OSINT media analyst. Return ONLY valid JSON.\n"
        "Language policy: ALL commentary fields in English.\n"
        "Task: analyze state-vs-exile narratives related to negotiations, agreements, ceasefire framing, and rhetorical positioning.\n"
        "Be exhaustive on passages in the provided records. Do not invent quotes.\n"
        "Output schema:\n"
        "{\n"
        '  "theme_clusters": [\n'
        '    {"theme":"...", "summary":"...", "passage_count":3, "consistency":"high|medium|low"}\n'
        "  ],\n"
        '  "quoted_passages": [\n'
        '    {"quote":"full quote or excerpt", "source_name":"...", "timing":"ISO/unknown", "context_note":"...", "theme":"..."}\n'
        "  ],\n"
        '  "negotiation_narrative_score": 0-100,\n'
        '  "method_notes": ["short methodological note"]\n'
        "}\n"
        "Rules:\n"
        "- quoted_passages must include source_name.\n"
        "- If timing is unknown, set timing to 'unknown'.\n"
        "- Do not include markdown code fences.\n"
        f"Conflict: {conflict}\n"
        f"MAX_QUOTES: {SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES}\n"
        f"INPUT_ITEMS_JSON: {payload[:50000]}"
    )


def _deterministic_deep_fallback(
    state_items: List[Dict[str, Any]],
    exile_items: List[Dict[str, Any]],
    reaction_signals: List[str],
    latency_hours: Optional[float],
) -> Dict[str, Any]:
    state_n = len(state_items)
    exile_n = len(exile_items)
    score = 50.0
    if state_n and exile_n:
        score += 10
    if latency_hours is not None and latency_hours > 8:
        score -= 8
    score -= min(15, len(reaction_signals) * 4)
    score = max(0.0, min(100.0, round(score, 1)))

    themes: List[Dict[str, Any]] = [
        {
            "theme": "State_vs_exile_framing",
            "summary": "Framing differences indicate contested interpretation of negotiation and ceasefire signals.",
            "passage_count": min(6, state_n + exile_n),
            "consistency": "medium" if state_n and exile_n else "low",
        }
    ]
    quotes: List[Dict[str, Any]] = []
    for row in (state_items[:3] + exile_items[:3])[:SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES]:
        txt = str(row.get("title") or row.get("text") or "").strip()
        src = str(row.get("source_name") or "").strip()
        if not txt or not src:
            continue
        quotes.append(
            {
                "quote": txt[:420],
                "source_name": src[:120],
                "timing": "unknown",
                "context_note": "Fallback extraction from feed headlines/snippets.",
                "theme": "State_vs_exile_framing",
            }
        )
    notes = [
        "Deterministic fallback used (Gemini unavailable or invalid response).",
        "Quotes are constrained to fetched feed snippets and may be partial.",
    ]
    return {
        "theme_clusters": themes,
        "quoted_passages": quotes,
        "negotiation_narrative_score": score,
        "method_notes": notes,
    }


def _run_gemini_deep_analysis(
    conflict: str,
    state_items: List[Dict[str, Any]],
    exile_items: List[Dict[str, Any]],
    reaction_signals: List[str],
    latency_hours: Optional[float],
) -> Dict[str, Any]:
    if not SIGNAL_FRAMEWORK_GEMINI_DEEP_ANALYSIS:
        out = _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)
        out["method_notes"].append("Gemini deep analysis disabled by feature flag.")
        return out
    try:
        from services.gemini_service import run_gemini_research
    except Exception:
        return _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)

    items = _prepare_gemini_items(state_items, exile_items)
    if not items:
        out = _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)
        out["method_notes"].append("No feed items available for deep analysis input.")
        return out

    prompt = _build_gemini_prompt(conflict, items)
    resp = run_gemini_research(prompt)
    parsed = resp.parsed_json if isinstance(resp.parsed_json, dict) else {}
    if not parsed:
        return _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)

    themes_raw = parsed.get("theme_clusters")
    quotes_raw = parsed.get("quoted_passages")
    notes_raw = parsed.get("method_notes")
    score_raw = parsed.get("negotiation_narrative_score")

    themes: List[Dict[str, Any]] = []
    if isinstance(themes_raw, list):
        for t in themes_raw[:8]:
            if not isinstance(t, dict):
                continue
            theme = str(t.get("theme") or "").strip()
            summary = str(t.get("summary") or "").strip()
            if not theme or not summary:
                continue
            try:
                passage_count = int(t.get("passage_count") or 0)
            except Exception:
                passage_count = 0
            consistency = str(t.get("consistency") or "medium").lower()
            if consistency not in ("high", "medium", "low"):
                consistency = "medium"
            themes.append(
                {
                    "theme": theme[:120],
                    "summary": summary[:400],
                    "passage_count": max(0, passage_count),
                    "consistency": consistency,
                }
            )

    quotes: List[Dict[str, Any]] = []
    if isinstance(quotes_raw, list):
        for q in quotes_raw[:SIGNAL_FRAMEWORK_GEMINI_MAX_QUOTES]:
            if not isinstance(q, dict):
                continue
            source_name = str(q.get("source_name") or "").strip()
            quote = str(q.get("quote") or "").strip()
            if not source_name or not quote:
                continue
            quotes.append(
                {
                    "quote": quote[:900],
                    "source_name": source_name[:120],
                    "timing": str(q.get("timing") or "unknown")[:80],
                    "context_note": str(q.get("context_note") or "")[:300],
                    "theme": str(q.get("theme") or "")[:120],
                }
            )

    notes: List[str] = []
    if isinstance(notes_raw, list):
        notes = [str(x)[:220] for x in notes_raw if isinstance(x, str)][:6]
    if not notes:
        notes = ["Gemini deep analysis based on fetched state/exile feed snippets."]
    if resp.error:
        notes.append(f"Gemini note: {resp.error}")

    try:
        score = float(score_raw)
    except Exception:
        score = _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)[
            "negotiation_narrative_score"
        ]
    score = max(0.0, min(100.0, round(score, 1)))

    if not themes:
        themes = _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)["theme_clusters"]
    if not quotes:
        quotes = _deterministic_deep_fallback(state_items, exile_items, reaction_signals, latency_hours)["quoted_passages"]

    return {
        "theme_clusters": themes,
        "quoted_passages": quotes,
        "negotiation_narrative_score": score,
        "method_notes": notes,
    }


def run_signal_framework_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run the Signal Framework: compare state vs exile/independent sources,
    compute lexical, latency, discrepancy, and reaction signals; return structured report in English.
    """
    profile = _source_profile_for_conflict(conflict)
    if not profile:
        return SignalFrameworkReport(
            conflict=conflict,
            synthesis_text="Signal Framework is configured for Iran and Lebanon narrative comparison. No analysis run.",
            error="conflict_not_supported",
        ).model_dump(mode="json")
    camp_a_label = profile.get("camp_a_label") or "State / Official"
    camp_b_label = profile.get("camp_b_label") or "Exile / Independent"
    camp_a_sources = list(profile.get("camp_a_sources") or [])
    camp_b_sources = list(profile.get("camp_b_sources") or [])
    english_camp_b_source = profile.get("english_camp_b_source") or ENGLISH_EXILE_SOURCE
    camp_a_source_names = {s["name"] for s in camp_a_sources}

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            state_futures = [
                executor.submit(_fetch_feed, s["url"], s["name"], camp_a_source_names) for s in camp_a_sources
            ]
            exile_futures = [
                executor.submit(_fetch_feed, s["url"], s["name"], camp_a_source_names) for s in camp_b_sources
            ]

            source_results: List[SourceResult] = []
            state_items: List[Dict[str, Any]] = []
            for s, fut in zip(camp_a_sources, state_futures, strict=True):
                try:
                    items = fut.result(timeout=20) or []
                    items = _apply_source_whitelist(items, list(s.get("allowed_domains") or []))
                    state_items.extend(items)
                    source_results.append(
                        SourceResult(
                            name=s["name"],
                            status="ok" if items else "degraded",
                            record_count=len(items),
                            fetched_at=utc_now_iso(),
                            reference_urls=[s["url"]],
                            endpoint_kind="rss" if "rss" in s["url"].lower() or "xml" in s["url"].lower() else "html",
                        )
                    )
                except Exception as e:
                    logger.debug("SignalFramework: state feed failed: %s", e)
                    source_results.append(
                        SourceResult(name=s["name"], status="error", error=str(e), fetched_at=utc_now_iso())
                    )

            exile_items: List[Dict[str, Any]] = []
            for s, fut in zip(camp_b_sources, exile_futures, strict=True):
                try:
                    items = fut.result(timeout=20) or []
                    items = _apply_source_whitelist(items, list(s.get("allowed_domains") or []))
                    exile_items.extend(items)
                    source_results.append(
                        SourceResult(
                            name=s["name"],
                            status="ok" if items else "degraded",
                            record_count=len(items),
                            fetched_at=utc_now_iso(),
                            reference_urls=[s["url"]],
                            endpoint_kind="rss" if "rss" in s["url"].lower() or "xml" in s["url"].lower() else "html",
                        )
                    )
                except Exception as e:
                    logger.debug("SignalFramework: exile feed failed: %s", e)
                    source_results.append(
                        SourceResult(name=s["name"], status="error", error=str(e), fetched_at=utc_now_iso())
                    )

            reg = get_health_registry()
            if reg:
                for sr in source_results:
                    reg.record_result(sr.name, "narrative", sr)

        # Prioritize conflict/war-relevant rows so state feed is not dominated by culture soft-news.
        state_items = _prioritize_war_items(state_items)
        exile_items = _prioritize_war_items(exile_items)

        # Prefer English exile source (Iran International) for display so UI can show English first
        exile_items_sorted = sorted(
            exile_items,
            key=lambda x: (0 if x.get("source_name") == english_camp_b_source else 1, -(x.get("published_ts") or 0)),
        )
        english_exile_items = [i for i in exile_items if i.get("source_name") == english_camp_b_source]

        # Lexical signal
        state_terms = _extract_key_terms(state_items)
        exile_terms = _extract_key_terms(exile_items)
        exile_terms_en = _extract_key_terms(english_exile_items) if english_exile_items else exile_terms

        main_state = state_items[0].get("title", "") if state_items else ""
        main_exile = (exile_items_sorted[0].get("title", "") if exile_items_sorted else "")[:400]
        main_exile_en = (english_exile_items[0].get("title", "") if english_exile_items else main_exile)[:400]
        if not main_exile_en and main_exile:
            main_exile_en = main_exile  # fallback to any

        # Ensure display is in English: prefer _en; if content is Farsi, use placeholder
        main_state_display, main_exile_display = _ensure_english_display(main_state, main_exile, main_exile_en)

        state_terms_str = ", ".join(state_terms[:15]) if state_terms else "—"
        exile_terms_str = ", ".join(exile_terms[:15]) if exile_terms else "—"
        exile_terms_en_str = ", ".join(exile_terms_en[:15]) if exile_terms_en else ""
        if exile_terms_en_str and _is_mostly_farsi(exile_terms_en_str):
            exile_terms_en_str = "Key terms in Farsi (no English translation in this run)."
        elif not exile_terms_en_str and exile_terms_str and not _is_mostly_farsi(exile_terms_str):
            exile_terms_en_str = exile_terms_str
        elif not exile_terms_en_str and exile_terms_str:
            exile_terms_en_str = "Key terms in Farsi (no English translation in this run)."
        key_state_display = state_terms_str if state_terms_str != "—" else None
        key_exile_display = exile_terms_en_str or None

        source_reliability_tier = "api"
        endpoint_kinds = {str(s.endpoint_kind or "").lower() for s in source_results}
        if "html" in endpoint_kinds:
            source_reliability_tier = "html-scrape"
        elif "rss" in endpoint_kinds:
            source_reliability_tier = "rss"
        if not source_results:
            source_reliability_tier = "inferred"
        verification_state = (
            "confirmed"
            if state_items and exile_items and source_reliability_tier in {"api", "rss"}
            else "partially_confirmed"
            if (state_items or exile_items)
            else "contested"
        )

        claim_conflicts: List[str] = []
        state_l = (main_state or "").lower()
        exile_l = (main_exile or "").lower()
        if ("civilian" in state_l and "military" in exile_l) or ("military" in state_l and "civilian" in exile_l):
            claim_conflicts.append("Target-type framing differs (civilian vs military).")
        if ("south lebanon" in state_l and "beirut" in exile_l) or ("south lebanon" in exile_l and "beirut" in state_l):
            claim_conflicts.append("Primary location framing differs (South Lebanon vs Beirut area).")
        if ("denied" in state_l and ("confirmed" in exile_l or "claimed" in exile_l)) or (
            "denied" in exile_l and ("confirmed" in state_l or "claimed" in state_l)
        ):
            claim_conflicts.append("One camp denial conflicts with confirmation language from the other.")

        # Stricter claim matching: compare numeric loss claims for IDF/Hezbollah across camps.
        camp_a_claims = _camp_claim_digest(state_items)
        camp_b_claims = _camp_claim_digest(exile_items)
        for key, a_val in camp_a_claims.items():
            if key not in camp_b_claims:
                continue
            b_val = camp_b_claims[key]
            diff = abs(a_val - b_val)
            # Strong mismatch threshold: both relative and absolute gap.
            if diff >= 5 and diff >= max(3, int(0.35 * max(a_val, b_val))):
                actor, metric = key
                claim_conflicts.append(
                    f"Loss claim mismatch for {actor.upper()} {metric}: camp A reports {a_val}, camp B reports {b_val}."
                )
        if claim_conflicts:
            verification_state = "contested"

        table = [
            SourceComparisonRow(
                point="Main claim",
                state_narrative=main_state[:400] if main_state else "No state coverage retrieved.",
                exile_narrative=main_exile or "No exile/independent coverage retrieved.",
                state_narrative_en=main_state_display,
                exile_narrative_en=main_exile_display,
                source_reliability_tier=source_reliability_tier,
                verification_state=verification_state,
            ),
            SourceComparisonRow(
                point="Key terms",
                state_narrative=state_terms_str,
                exile_narrative=exile_terms_str,
                state_narrative_en=key_state_display,
                exile_narrative_en=key_exile_display,
                source_reliability_tier=source_reliability_tier,
                verification_state=verification_state,
            ),
        ]

        # Latency signal (timestamps now have fallback to fetch time, so we get values when we have items)
        ts_state = _first_mention_ts(state_items)
        ts_exile = _first_mention_ts(exile_items)
        latency_str = "Not enough timestamps to compare (need items from both state and exile feeds)."
        latency_hours: Optional[float] = None
        if ts_state is not None and ts_exile is not None:
            diff_sec = abs(ts_state - ts_exile)
            latency_hours = diff_sec / 3600.0
            t_state_utc = (
                datetime.fromtimestamp(ts_state, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ts_state else ""
            )
            t_exile_utc = (
                datetime.fromtimestamp(ts_exile, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ts_exile else ""
            )
            if ts_state < ts_exile:
                latency_str = f"State media reported first (≈{latency_hours:.1f}h before exile). Earliest state: {t_state_utc} UTC, exile: {t_exile_utc} UTC."
            else:
                latency_str = f"Exile/independent media reported first (≈{latency_hours:.1f}h before state). Earliest exile: {t_exile_utc} UTC, state: {t_state_utc} UTC. Information vacuum on state side possible."
        elif ts_state is not None and state_items:
            t = datetime.fromtimestamp(ts_state, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            latency_str = f"State earliest: {t} UTC. No exile timestamps to compare (exile feeds may lack dates)."
        elif ts_exile is not None and exile_items:
            t = datetime.fromtimestamp(ts_exile, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            latency_str = f"Exile earliest: {t} UTC. No state coverage—state feeds returned no items."
        elif not state_items and exile_items:
            latency_str = "No state coverage; cannot compute latency. State feeds (IRNA, Fars, Tasnim, Press TV) returned no items (often geo-restricted)."

        # Reaction signal
        reaction_signals = _detect_reaction_signals(state_items)
        discrepancy_note = "No automated discrepancy check; compare narratives with social/media imagery manually."
        credibility_gaps = discrepancy_note
        if reaction_signals:
            credibility_gaps = "State framing shows defensive or denial language. " + discrepancy_note

        # Synthesis
        prob, synth_text = _synthesis_confidence(state_items, exile_items, latency_hours, reaction_signals)
        deep = _run_gemini_deep_analysis(conflict, state_items, exile_items, reaction_signals, latency_hours)

        # Anomalies: explain state vs exile availability
        anomalies: List[str] = []
        if not state_items and not exile_items:
            anomalies.append("No items from either camp—check feed availability or filters.")
        elif state_items and not exile_items:
            anomalies.append("Only state-side coverage available; exile/independent feeds may be blocked or down.")
        elif exile_items and not state_items:
            anomalies.append(
                "Only exile-side coverage available. State feeds (IRNA, Fars, Tasnim, Press TV) returned no items—"
                "often geo-restricted outside Iran or temporarily unavailable."
            )

        signals = SignalSummary(
            lexical={
                "state_terms": state_terms[:15],
                "exile_terms": exile_terms[:15],
                "interpretation": "Compare terms: state framing (e.g. rioter/sedition) vs exile framing (e.g. demonstrator/crackdown) reveals narrative intent.",
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
            camp_a_label=camp_a_label,
            camp_b_label=camp_b_label,
            source_reliability_tier=source_reliability_tier,
            verification_state=verification_state,
            claim_conflicts=claim_conflicts,
            anomalies=anomalies,
            lexical_state_terms=state_terms[:15],
            lexical_exile_terms=exile_terms[:15],
            reaction_signals=reaction_signals,
            theme_clusters=deep.get("theme_clusters") or [],
            quoted_passages=deep.get("quoted_passages") or [],
            negotiation_narrative_score=deep.get("negotiation_narrative_score"),
            method_notes=deep.get("method_notes") or [],
            state_item_count=len(state_items),
            exile_item_count=len(exile_items),
        )
        report.method_notes.append(
            "State/exile rows are war-prioritized to suppress culture/soft-news drift in conflict analysis."
        )
        return report.model_dump(mode="json")
    except Exception as e:
        logger.exception("SignalFramework: run failed for conflict '%s': %s", conflict, e)
        return SignalFrameworkReport(
            conflict=conflict,
            error=str(e),
            synthesis_text="Signal Framework analysis failed.",
        ).model_dump(mode="json")
