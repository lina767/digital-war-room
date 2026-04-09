"""
SOCMINT Agent orchestration.

Data collection and parsing live in fetchers/socmint_fetchers.py.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, wait
from typing import Any, Dict, List, Optional

from .config import USE_RULE_BASED_AGENTS
from .contracts import get_agent_fallback
from .fetchers.socmint_fetchers import (
    _run_socmint_ner,
    fetch_reliefweb_reports,
    fetch_rss_feeds,
    scrape_telegram_channels,
    scrape_twitter_nitter,
    search_reddit,
)
from .health_registry import get_health_registry
from .llm import run_tool_agent
from .utils import SourceResult, build_agent_meta, cap_reference_urls, run_async, utc_now_iso

logger = logging.getLogger(__name__)
SOCMINT_SOURCE_TIMEOUT_SEC = max(5, int(os.getenv("SOCMINT_SOURCE_TIMEOUT_SEC", "20")))


def _run_rule_based_socmint(conflict: str) -> Dict[str, Any]:
    start = time.perf_counter()
    fetched_at = utc_now_iso()
    try:
        executor = ThreadPoolExecutor(max_workers=5)
        fut_by_name = {
            "telegram": executor.submit(scrape_telegram_channels, conflict=conflict),
            "twitter": executor.submit(scrape_twitter_nitter, conflict=conflict),
            "reddit": executor.submit(search_reddit, conflict=conflict),
            "rss": executor.submit(fetch_rss_feeds, conflict=conflict),
            "reliefweb": executor.submit(fetch_reliefweb_reports, conflict=conflict),
        }
        done, _ = wait(set(fut_by_name.values()), timeout=SOCMINT_SOURCE_TIMEOUT_SEC)
        rows: Dict[str, List[Dict[str, Any]]] = {
            "telegram": [],
            "twitter": [],
            "reddit": [],
            "rss": [],
            "reliefweb": [],
        }
        for name, fut in fut_by_name.items():
            if fut not in done:
                logger.info("SOCMINT source timed out: %s (budget=%ss)", name, SOCMINT_SOURCE_TIMEOUT_SEC)
                continue
            try:
                data = fut.result(timeout=0)
            except TimeoutError:
                logger.info("SOCMINT source timed out at result(): %s", name)
                continue
            except Exception as exc:
                logger.info("SOCMINT source failed: %s (%s)", name, exc)
                continue
            rows[name] = [p for p in (data or []) if isinstance(p, dict) and "error" not in p]
        # Do not block on stragglers; keep run latency bounded.
        executor.shutdown(wait=False, cancel_futures=True)
        telegram = rows["telegram"]
        twitter = rows["twitter"]
        reddit = rows["reddit"]
        rss = rows["rss"]
        reliefweb = rows["reliefweb"]

        all_posts = telegram + twitter + reddit + rss + reliefweb

        try:
            from services.hf_service import deduplicate_items

            all_posts = run_async(
                deduplicate_items(
                    all_posts,
                    text_key="text",
                    threshold=0.92,
                    source="socmint",
                    conflict=conflict,
                )
            )
        except Exception as e:
            logger.debug("HF semantic dedup unavailable in SOCMINT: %s", e)

        escalatory = sum(1 for p in all_posts if p.get("sentiment_label") == "ESCALATORY")
        de_esc = sum(1 for p in all_posts if p.get("sentiment_label") == "DE-ESCALATORY")
        sent_sum = sum(p.get("sentiment_score", 0) for p in all_posts)
        overall_sentiment = (sent_sum / len(all_posts)) if all_posts else 0.0

        base = 30.0
        priority_accounts = ("sentdefcon", "OSINTdefender", "WarMonitor3")
        twitter_esc = sum(
            1
            for p in twitter
            if p.get("sentiment_label") == "ESCALATORY" and p.get("account") in priority_accounts
        )
        base += min(50, twitter_esc * 8)
        base += min(20, len(reliefweb) * 10)
        telegram_channels_with_esc = len({p.get("source", "") for p in telegram if p.get("sentiment_label") == "ESCALATORY"})
        base += min(24, telegram_channels_with_esc * 6)
        base += min(30, max(0, escalatory - twitter_esc) * 3)
        base -= de_esc * 2
        reddit_high = sum(1 for p in reddit if p.get("upvotes", 0) > 1000)
        base += min(15, reddit_high * 5)
        score = max(0.0, min(100.0, base))

        top_signals = []
        for p in sorted(
            all_posts,
            key=lambda x: (
                1 if x.get("account") in priority_accounts else 0,
                x.get("sentiment_score", 0),
                x.get("upvotes", 0),
            ),
            reverse=True,
        )[:6]:
            t = p.get("text") or p.get("title") or p.get("body_excerpt") or ""
            if t:
                prefix = f"[{p.get('source', 'signal')}] "
                body = t[:110] + ("..." if len(t) > 110 else "")
                top_signals.append(prefix + body)

        entities = _run_socmint_ner(all_posts)

        duration_ms = int((time.perf_counter() - start) * 1000)
        telegram_urls = [p.get("url") for p in telegram if isinstance(p, dict) and isinstance(p.get("url"), str)]
        twitter_urls = [p.get("url") for p in twitter if isinstance(p, dict) and isinstance(p.get("url"), str)]
        reddit_urls = [p.get("url") for p in reddit if isinstance(p, dict) and isinstance(p.get("url"), str)]
        rss_urls = [p.get("url") for p in rss if isinstance(p, dict) and isinstance(p.get("url"), str)]
        reliefweb_urls = [
            p.get("url") for p in reliefweb if isinstance(p, dict) and isinstance(p.get("url"), str)
        ]
        source_results = [
            SourceResult(
                name="Telegram",
                status="ok" if telegram else "error",
                fetched_at=fetched_at,
                record_count=len(telegram),
                reference_urls=cap_reference_urls(telegram_urls),
                endpoint_kind="html",
            ),
            SourceResult(
                name="Twitter/Nitter",
                status="ok" if twitter else "error",
                fetched_at=fetched_at,
                record_count=len(twitter),
                reference_urls=cap_reference_urls(twitter_urls),
                endpoint_kind="html",
            ),
            SourceResult(
                name="Reddit",
                status="ok" if reddit else "error",
                fetched_at=fetched_at,
                record_count=len(reddit),
                reference_urls=cap_reference_urls(reddit_urls),
                endpoint_kind="rest",
            ),
            SourceResult(
                name="RSS",
                status="ok" if rss else "error",
                fetched_at=fetched_at,
                record_count=len(rss),
                reference_urls=cap_reference_urls(rss_urls),
                endpoint_kind="rss",
            ),
            SourceResult(
                name="ReliefWeb",
                status="ok" if reliefweb else "error",
                fetched_at=fetched_at,
                record_count=len(reliefweb),
                reference_urls=cap_reference_urls(reliefweb_urls),
                endpoint_kind="rest",
            ),
        ]
        reg = get_health_registry()
        if reg:
            for sr in source_results:
                reg.record_result(sr.name, "socmint", sr)

        return {
            "conflict": conflict,
            "telegram_posts": telegram,
            "twitter_posts": twitter,
            "reddit_posts": reddit,
            "rss_articles": rss,
            "reliefweb_reports": reliefweb,
            "total_signals": len(all_posts),
            "escalatory_count": escalatory,
            "de_escalatory_count": de_esc,
            "overall_sentiment": round(overall_sentiment, 4),
            "socmint_score": round(score, 1),
            "top_signals": top_signals,
            "entities": entities,
            "summary": f"SOCMINT (rule-based): {len(all_posts)} signals ({escalatory} escalatory, {de_esc} de-escalatory). Score {score:.0f}.",
            "_meta": build_agent_meta(
                "socmint",
                fetched_at,
                duration_ms,
                source_results,
                has_any_data=bool(all_posts),
            ),
        }
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fb = get_agent_fallback("socmint")
        fb["conflict"] = conflict
        fb["socmint_score"] = 30.0
        fb["summary"] = "SOCMINT data unavailable."
        fb["overall_sentiment"] = 0.0
        fb["_meta"] = build_agent_meta(
            "socmint",
            fetched_at,
            duration_ms,
            [],
            fallback_used=True,
            error_summary=str(e),
            has_any_data=False,
        )
        return fb


SOCMINT_SYSTEM = """You are a SOCMINT (Social Media Intelligence) analyst.
Your job: monitor Telegram, Twitter (Nitter), Reddit, RSS, and ReliefWeb for conflict signals, then compute a SOCMINT score (0-100).

Always call all five tools: scrape_telegram_channels, scrape_twitter_nitter, search_reddit, fetch_rss_feeds, fetch_reliefweb_reports. Then analyze the combined data.

Scoring rules:
- Base: 30
- Verified OSINT Twitter accounts (sentdefcon, OSINTdefender): +8 per escalatory post
- ReliefWeb emergency reports: +10 each (max +20) — humanitarian crisis = escalation signal
- Telegram channel active + escalatory: +6 per channel (max +24)
- Each other escalatory post/article: +3 (max +30)
- Each de-escalatory signal: -2
- High-upvote Reddit posts (>1000): +5 each (max +15)
- Clamp to [0, 100]

Return ONLY valid JSON:
{
  "telegram_posts": [...],
  "twitter_posts": [...],
  "reddit_posts": [...],
  "rss_articles": [...],
  "reliefweb_reports": [...],
  "total_signals": <number>,
  "escalatory_count": <number>,
  "de_escalatory_count": <number>,
  "overall_sentiment": <number -1 to 1>,
  "socmint_score": <number>,
  "top_signals": ["<key signal>", ...],
  "summary": "<1-2 sentence summary>"
}
No markdown, no explanation, just JSON."""


def run_socmint_agent(conflict: str, peers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_socmint(conflict)

    tool_fns = {
        "scrape_telegram_channels": scrape_telegram_channels,
        "scrape_twitter_nitter": scrape_twitter_nitter,
        "search_reddit": search_reddit,
        "fetch_rss_feeds": fetch_rss_feeds,
        "fetch_reliefweb_reports": fetch_reliefweb_reports,
    }
    tool_schemas = [
        {
            "name": "scrape_telegram_channels",
            "description": "Scrape Telegram channels for conflict signals.",
            "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
        },
        {
            "name": "scrape_twitter_nitter",
            "description": "Scrape Twitter/Nitter for conflict signals.",
            "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
        },
        {
            "name": "search_reddit",
            "description": "Search Reddit for conflict-related posts.",
            "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
        },
        {
            "name": "fetch_rss_feeds",
            "description": "Fetch curated RSS feeds for conflict analysis.",
            "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
        },
        {
            "name": "fetch_reliefweb_reports",
            "description": "Fetch ReliefWeb humanitarian reports.",
            "input_schema": {"type": "object", "properties": {"conflict": {"type": "string"}}, "required": ["conflict"]},
        },
    ]

    text = run_tool_agent(
        system=SOCMINT_SYSTEM,
        user_content=f"Monitor social media and open sources for conflict: {conflict}",
        tool_fns=tool_fns,
        tool_schemas=tool_schemas,
        max_rounds=6,
    )
    if text:
        text = text.strip()
        for prefix in ("```json", "```"):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        try:
            result = json.loads(text)
            result["conflict"] = conflict
            return result
        except json.JSONDecodeError as exc:
            logger.warning("SOCMINT: tool-agent returned invalid JSON, falling back to rule-based parser: %s", exc)

    return _run_rule_based_socmint(conflict)
