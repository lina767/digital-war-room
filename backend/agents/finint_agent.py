"""
FININT Agent – LangChain Tool-Calling Agent
Fetches Brent/WTI oil prices, Polymarket conflict odds, and tracked wallet positions.
- Gamma API: https://gamma-api.polymarket.com (events, markets)
- Data API:  https://data-api.polymarket.com (positions, activity)
Optional: set POLYMARKET_BUILDER_API_KEY in .env (your personal builder API key) for authenticated requests.
"""
import asyncio
import os
from typing import Any, Dict, List

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"

# Optional: POLYMARKET_BUILDER_API_KEY in .env for authenticated requests (e.g. higher rate limits).
def _polymarket_headers() -> Dict[str, str]:
    """Optional headers when POLYMARKET_BUILDER_API_KEY is set (your personal builder API key)."""
    key = os.getenv("POLYMARKET_BUILDER_API_KEY")
    if not key or not key.strip():
        return {}
    return {"Authorization": f"Bearer {key.strip()}"}

# Tracked wallets: (label, proxy wallet address). Use proxy address from profile URL.
TRACKED_WALLETS: List[tuple[str, str]] = [
    ("rundeep", "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"),
]

# Explicit Polymarket markets to always track (FININT) – fetched by slug via Gamma API
TRACKED_POLYMARKET_SLUGS = [
    "usisrael-strikes-iran-on",           # US/Israel strikes Iran on...?
    "us-x-iran-ceasefire-by",              # US x Iran ceasefire by...?
    "will-the-iranian-regime-fall-by-the-end-of-2026",  # Will the Iranian regime fall before 2027?
]

POLYMARKET_KEYWORDS = [
    # Iran/Middle East
    "iran", "iranian", "irgc", "tehran", "nuclear", "khamenei",
    "israel", "israeli", "gaza", "hezbollah", "hamas",
    "persian gulf", "strait of hormuz", "airstrike", "strike on",
    # Military/War
    "war", "attack", "military", "missile", "troops", "invasion",
    "conflict", "escalat", "ceasefire",
    # US foreign policy
    "sanctions", "us-iran", "middle east",
]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _normalize_polymarket_item(m: dict, slug: str = "") -> dict | None:
    """Build {question, probability, volume, url} from Gamma API event or market object."""
    question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
    if not question:
        return None
    prices = m.get("outcomePrices") or []
    prob = 0.0
    if prices:
        prob = max((_safe_float(p) or 0) for p in prices)
    for token in m.get("tokens") or []:
        p = _safe_float(token.get("price"))
        if p and p > prob:
            prob = p
    volume = _safe_float(m.get("volume") or m.get("volumeNum") or m.get("liquidity") or 0) or 0
    url_slug = slug or m.get("slug") or ""
    return {
        "question": question,
        "probability": round(prob, 3),
        "volume": round(volume, 0),
        "url": f"https://polymarket.com/event/{url_slug}" if url_slug else "",
    }


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def get_brent_price() -> Dict[str, Any]:
    """Fetch current Brent crude oil price and daily change from Alpha Vantage."""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ALPHAVANTAGE_URL, params={
                "function": "BRENT", "interval": "daily", "apikey": api_key
            })
            resp.raise_for_status()
            return resp.json()

    try:
        data = asyncio.run(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = _safe_float(latest.get("value"))
        prev_price = _safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price and prev_price else None
        return {
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "as_of": latest.get("date", ""),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_wti_price() -> Dict[str, Any]:
    """Fetch current WTI crude oil price and daily change from Alpha Vantage."""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ALPHAVANTAGE_URL, params={
                "function": "WTI", "interval": "daily", "apikey": api_key
            })
            resp.raise_for_status()
            return resp.json()

    try:
        data = asyncio.run(_fetch())
        series = data.get("data", [])
        if len(series) < 2:
            return {"error": "Insufficient data"}
        latest = series[0]
        prev = series[1]
        price = _safe_float(latest.get("value"))
        prev_price = _safe_float(prev.get("value"))
        change_pct = ((price - prev_price) / prev_price * 100) if price and prev_price else None
        return {
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "as_of": latest.get("date", ""),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
def get_polymarket_conflict_odds(conflict: str) -> List[Dict[str, Any]]:
    """Fetch Polymarket prediction market odds: tracked Iran markets first, then keyword-matched events."""
    async def _fetch_tracked():
        """Fetch TRACKED_POLYMARKET_SLUGS via Gamma API GET /events/slug/{slug}. One row per event."""
        headers = _polymarket_headers()
        out = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for slug in TRACKED_POLYMARKET_SLUGS:
                try:
                    resp = await client.get(
                        f"{GAMMA_API_BASE}/events/slug/{slug}",
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        continue
                    event = resp.json()
                    if not isinstance(event, dict):
                        continue
                    question = (
                        event.get("title") or event.get("question") or event.get("name") or ""
                    ).strip()
                    if not question:
                        continue
                    # Max probability: top-level outcomePrices or across markets
                    prob = 0.0
                    for p in event.get("outcomePrices") or []:
                        v = _safe_float(p)
                        if v and v > prob:
                            prob = v
                    for market in event.get("markets") or []:
                        if not isinstance(market, dict):
                            continue
                        for p in market.get("outcomePrices") or []:
                            v = _safe_float(p)
                            if v and v > prob:
                                prob = v
                        for token in market.get("tokens") or []:
                            v = _safe_float(token.get("price"))
                            if v and v > prob:
                                prob = v
                    volume = _safe_float(
                        event.get("volume") or event.get("volumeNum") or event.get("liquidity") or 0
                    ) or 0
                    out.append({
                        "question": question,
                        "probability": round(prob, 3),
                        "volume": round(volume, 0),
                        "url": f"https://polymarket.com/event/{slug}",
                    })
                except Exception:
                    continue
        return out

    async def _fetch_all():
        headers = _polymarket_headers()
        results = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(
                    f"{GAMMA_API_BASE}/events",
                    params={"limit": 200, "active": "true", "closed": "false"},
                    headers=headers,
                )
                if resp.status_code == 200:
                    events = resp.json()
                    if isinstance(events, list):
                        results.extend(events)
            except Exception:
                pass
            try:
                resp2 = await client.get(
                    f"{GAMMA_API_BASE}/markets",
                    params={"limit": 200, "active": "true", "closed": "false"},
                    headers=headers,
                )
                if resp2.status_code == 200:
                    markets = resp2.json()
                    if isinstance(markets, list):
                        results.extend(markets)
            except Exception:
                pass
        return results

    try:
        tracked = asyncio.run(_fetch_tracked())
        tracked_questions = {str(t.get("question", ""))[:80] for t in tracked if t.get("question")}

        data = asyncio.run(_fetch_all())
        relevant = []
        seen = set()

        for m in data:
            question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
            if not question:
                continue
            key = question[:60]
            if key in seen:
                continue
            description = str(m.get("description") or "").lower()
            combined = f"{question.lower()} {description}"
            if not any(kw in combined for kw in POLYMARKET_KEYWORDS):
                continue
            if question[:80] in tracked_questions:
                continue
            seen.add(key)
            item = _normalize_polymarket_item(m)
            if item:
                item["url"] = f"https://polymarket.com/event/{m.get('slug', '')}"
                relevant.append(item)

        relevant.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        # Tracked first (order as in TRACKED_POLYMARKET_SLUGS), then up to 10 keyword matches
        return tracked + relevant[:10]
    except Exception as e:
        return [{"error": str(e)}]


@tool
def get_tracked_wallet_positions() -> List[Dict[str, Any]]:
    """Fetch current Polymarket positions for tracked wallets (e.g. rundeep) via Data API."""
    if not TRACKED_WALLETS:
        return []
    async def _fetch():
        out = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for label, address in TRACKED_WALLETS:
                try:
                    resp = await client.get(
                        f"{DATA_API_BASE}/positions",
                        params={"user": address, "limit": 50, "sortBy": "TOKENS", "sortDirection": "DESC"},
                        headers=_polymarket_headers(),
                    )
                    if resp.status_code != 200:
                        out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                        continue
                    data = resp.json()
                    positions = data if isinstance(data, list) else data.get("data", data.get("positions", []))
                    if not isinstance(positions, list):
                        positions = []
                    # Keep fields useful for conflict relevance
                    items = []
                    for p in positions[:20]:
                        title = p.get("title") or p.get("market") or p.get("question") or ""
                        size = _safe_float(p.get("size") or p.get("tokens") or 0)
                        avg_price = _safe_float(p.get("avgPrice") or p.get("price"))
                        items.append({
                            "title": title[:120] if title else "",
                            "size": round(size, 2) if size else 0,
                            "avgPrice": round(avg_price, 4) if avg_price else None,
                        })
                    out.append({
                        "wallet": label,
                        "address": address[:10] + "...",
                        "position_count": len(positions),
                        "positions": items,
                    })
                except Exception as e:
                    out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
        return out
    try:
        return asyncio.run(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


# ── Rule-based tool chain (fixed order; no LLM) ─────────────────────────────

def _run_rule_based_finint(conflict: str) -> Dict[str, Any]:
    """Execute FININT tool chain in fixed order: brent → wti → polymarket → tracked_wallets. No LLM."""
    brent = get_brent_price.invoke({})
    wti = get_wti_price.invoke({})
    polymarket = get_polymarket_conflict_odds.invoke({"conflict": conflict})
    tracked_wallets = get_tracked_wallet_positions.invoke({})
    if not isinstance(polymarket, list):
        polymarket = []
    if not isinstance(tracked_wallets, list):
        tracked_wallets = []

    base = 50.0
    if isinstance(brent, dict) and "error" not in brent and brent.get("change_pct"):
        cp = brent.get("change_pct") or "0%"
        if "+" in cp and "%" in cp:
            try:
                v = float(cp.replace("%", "").strip())
                if v > 5:
                    base += 15
                elif v > 2:
                    base += 8
            except ValueError:
                pass
        if "-" in cp:
            base -= 10
    if polymarket:
        max_prob = max((_safe_float(p.get("probability")) or 0) for p in polymarket if isinstance(p, dict) and "error" not in p)
        if max_prob and max_prob > 0.5:
            base += 20
        elif max_prob and max_prob > 0.3:
            base += 10
    score = max(0.0, min(100.0, base))

    return {
        "brent": brent if isinstance(brent, dict) and "error" not in brent else {"price": None, "change_pct": "0.0%", "as_of": ""},
        "wti": wti if isinstance(wti, dict) and "error" not in wti else {"price": None, "change_pct": "0.0%", "as_of": ""},
        "polymarket": [p for p in polymarket if isinstance(p, dict) and "error" not in p],
        "tracked_wallets": [w for w in tracked_wallets if isinstance(w, dict)],
        "escalation_score": round(score, 1),
        "summary": "FININT (rule-based): oil and Polymarket data from fixed tool chain.",
    }


# ── Agent ──────────────────────────────────────────────────────────────────

FININT_TOOLS = [get_brent_price, get_wti_price, get_polymarket_conflict_odds, get_tracked_wallet_positions]

FININT_SYSTEM = """You are a FININT (Financial Intelligence) analyst.
Your job: fetch oil prices, Polymarket conflict odds, and tracked wallet positions, then compute an escalation score (0-100).

Scoring rules:
- Base: 50
- Brent > +5%: +15, Brent +2-5%: +8, Brent negative: -10
- Polymarket conflict odds > 50%: +20, 30-50%: +10
- Tracked wallets with large conflict-related positions: consider in summary
- Clamp to [0, 100]

Always call all four tools, then return ONLY valid JSON:
{
  "brent": {"price": "...", "change_pct": "...", "as_of": "..."},
  "wti": {"price": "...", "change_pct": "...", "as_of": "..."},
  "polymarket": [...],
  "tracked_wallets": [{"wallet": "...", "position_count": N, "positions": [...]}],
  "escalation_score": <number>,
  "summary": "<1-2 sentence summary; mention if tracked wallets have conflict exposure>"
}
No markdown, no explanation, just JSON."""


def run_finint_agent(conflict: str) -> Dict[str, Any]:
    """Run FININT: either rule-based (fixed tool chain) or LLM-driven, depending on USE_RULE_BASED_AGENTS."""
    from .config import USE_RULE_BASED_AGENTS
    if USE_RULE_BASED_AGENTS:
        return _run_rule_based_finint(conflict)

    model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0).bind_tools(FININT_TOOLS)

    messages = [
        SystemMessage(content=FININT_SYSTEM),
        HumanMessage(content=f"Analyze financial indicators for conflict: {conflict}"),
    ]

    import json
    # Agentic loop
    for _ in range(5):
        response = model.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # Final answer: parse JSON (strip optional markdown code fence)
            try:
                content = response.content
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                text = (content or "").strip()
                for prefix in ("```json", "```"):
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                return json.loads(text)
            except Exception:
                break

        # Execute tool calls
        for tc in response.tool_calls:
            tool_map = {t.name: t for t in FININT_TOOLS}
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                args = tc.get("args", {})
                result = tool_fn.invoke(args)
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tc["id"],
                ))

    # Fallback: same fixed tool chain as rule-based mode
    return _run_rule_based_finint(conflict)


