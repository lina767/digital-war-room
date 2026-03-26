import asyncio
import csv
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

from ..utils import run_async, safe_float, utc_now_iso

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
EIA_BASE = "https://api.eia.gov/v2/seriesid"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"
FEAR_GREED_CNN_API_URL = (os.getenv("FEAR_GREED_CNN_API_URL") or "").strip() or None
FEAR_GREED_FALLBACK_URL = "https://api.alternative.me/fng/?limit=1"
METACULUS_API_BASE = "https://www.metaculus.com/api2/questions/"
KALSHI_API_BASE = os.getenv("KALSHI_API_BASE", "").strip()
METALS_API_BASE = "https://metals-api.com/api"
OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

TRACKED_WALLETS: List[tuple[str, str]] = [("rundeep", "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2")]
TRACKED_ETH_ADDRESSES: List[tuple[str, str]] = []
MAX_ETHERSCAN_ADDRESSES_PER_RUN = 20
ETHERSCAN_RATE_LIMIT_DELAY_SEC = 0.35

TRACKED_POLYMARKET_SLUGS = [
    "us-x-iran-ceasefire-by",
    "will-crude-oil-cl-hit-by-end-of-march",
    "us-forces-enter-iran-by",
    "kharg-island-no-longer-under-iranian-control-by-march-31",
    "trump-announces-end-of-military-operations-against-iran-by",
    "iran-x-israelus-conflict-ends-by",
    "will-the-iranian-regime-fall-by-june-30",
]

POLYMARKET_INCLUSION_KEYWORDS = {
    "conflicts": ["war", "military", "invasion", "ceasefire", "nato", "nuclear"],
    "countries": ["russia", "china", "iran", "israel"],
    "leaders": ["putin", "trump", "netanyahu"],
    "economics": ["fed", "interest rate", "inflation", "recession", "tariffs", "sanctions"],
    "global": ["un", "eu", "treaties", "summits", "coups"],
}
POLYMARKET_EXCLUSION_KEYWORDS = {
    "sports": ["nba", "nfl", "fifa", "world cup", "championships", "playoffs"],
    "entertainment": ["oscars", "movies", "celebrities", "tiktok", "streaming"],
}
POLYMARKET_INCLUDE_TERMS = tuple(
    term.lower() for terms in POLYMARKET_INCLUSION_KEYWORDS.values() for term in terms
)
POLYMARKET_EXCLUDE_TERMS = tuple(
    term.lower() for terms in POLYMARKET_EXCLUSION_KEYWORDS.values() for term in terms
)
POLYMARKET_MIN_HOURS_LEFT = 48

METACULUS_CONFLICT_TERMS = [
    "iran",
    "us-iran",
    "war",
    "military",
    "strike",
    "nuclear",
    "israel",
    "gaza",
    "ukraine",
    "russia",
    "taiwan",
    "china",
]
KALSHI_CONFLICT_TERMS = ["iran", "military", "strike", "nuclear", "israel", "gaza", "ukraine", "russia", "china", "taiwan"]

OFAC_CONFLICT_KEYWORDS: Dict[str, List[str]] = {
    "iran": ["iran", "irgc", "iranian", "tehran", "qods", "khamenei"],
    "us-iran": ["iran", "irgc", "iranian", "tehran"],
    "russia": ["russia", "russian", "ukraine", "donbas", "crimea", "putin"],
    "ukraine": ["ukraine", "russia", "donbas", "crimea"],
    "syria": ["syria", "syrian", "assad"],
    "north korea": ["dprk", "north korea", "kim jong"],
    "default": ["iran", "russia", "syria"],
}

_ofac_raw_csv: str | None = None
_ofac_cache_ts: float = 0.0
_ofac_previous_keys: set[str] = set()
OFAC_CACHE_TTL = 6 * 3600


def _from_price_points(points: List[tuple[float, str]]) -> Dict[str, Any]:
    if len(points) < 2:
        return {"error": "Insufficient data"}
    latest_price, latest_date = points[0]
    prev_price, _ = points[1]
    change_pct = ((latest_price - prev_price) / prev_price * 100) if prev_price else None
    return {"price": f"{latest_price:.2f}", "change_pct": _format_pct(change_pct), "as_of": latest_date}


def _fetch_alpha_series(function_name: str) -> Dict[str, Any]:
    api_key = (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()
    if not api_key:
        return {"error": "ALPHAVANTAGE_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(ALPHAVANTAGE_URL, params={"function": function_name, "interval": "daily", "apikey": api_key})
            resp.raise_for_status()
            return resp.json()

    data = run_async(_fetch())
    series = data.get("data", [])
    points: List[tuple[float, str]] = []
    for item in series:
        val = safe_float(item.get("value"))
        dt = str(item.get("date") or "")
        if val is None or not dt:
            continue
        points.append((val, dt))
        if len(points) >= 2:
            break
    return _from_price_points(points)


def _fetch_eia_spot(series_id: str) -> Dict[str, Any]:
    api_key = (os.getenv("EIA_API_KEY") or "").strip()
    if not api_key:
        return {"error": "EIA_API_KEY not set"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{EIA_BASE}/{series_id}",
                params={"api_key": api_key, "sort[0][column]": "period", "sort[0][direction]": "desc", "offset": 0, "length": 5},
            )
            resp.raise_for_status()
            return resp.json()

    data = run_async(_fetch())
    rows = (((data or {}).get("response") or {}).get("data") or [])
    points: List[tuple[float, str]] = []
    for row in rows:
        val = safe_float(row.get("value"))
        period = str(row.get("period") or "")
        if val is None or not period:
            continue
        points.append((val, period))
        if len(points) >= 2:
            break
    return _from_price_points(points)


def _fetch_fred_series(series_id: str) -> Dict[str, Any]:
    fred_key = (os.getenv("FRED_API_KEY") or "").strip()
    params = {"series_id": series_id, "file_type": "json", "sort_order": "desc", "limit": 5}
    if fred_key:
        params["api_key"] = fred_key

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            return resp.json()

    data = run_async(_fetch())
    rows = (data or {}).get("observations") or []
    points: List[tuple[float, str]] = []
    for row in rows:
        value = str(row.get("value") or "").strip()
        if not value or value == ".":
            continue
        val = safe_float(value)
        dt = str(row.get("date") or "")
        if val is None or not dt:
            continue
        points.append((val, dt))
        if len(points) >= 2:
            break
    return _from_price_points(points)


def _polymarket_headers() -> Dict[str, str]:
    key = os.getenv("POLYMARKET_BUILDER_API_KEY")
    if not key or not key.strip():
        return {}
    return {"Authorization": f"Bearer {key.strip()}"}


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _clamp_prob(prob: float) -> float:
    if prob > 1.0:
        prob = prob / 100.0
    return max(0.0, min(1.0, prob))


def _matches_prediction_market_filters(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    if any(excl in lowered for excl in POLYMARKET_EXCLUDE_TERMS):
        return False
    return any(incl in lowered for incl in POLYMARKET_INCLUDE_TERMS)


def _extract_end_date(m: dict) -> str | None:
    raw = m.get("endDate") or m.get("end_date") or m.get("closedTime") or m.get("end_date_iso")
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        return str(raw)


def _polymarket_end_ok(m: dict) -> bool:
    end_raw = m.get("endDate") or m.get("end_date") or m.get("closedTime") or m.get("end_date_iso")
    if not end_raw:
        return True
    try:
        if isinstance(end_raw, (int, float)):
            end_dt = datetime.fromtimestamp(end_raw, tz=timezone.utc)
        else:
            end_str = str(end_raw).replace("Z", "+00:00")[:19]
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        cutoff = (datetime.now(timezone.utc) + timedelta(hours=POLYMARKET_MIN_HOURS_LEFT)).isoformat()[:19]
        return end_dt.isoformat()[:19] >= cutoff
    except Exception:
        return True


def _normalize_polymarket_item(m: dict, slug: str = "") -> dict | None:
    question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
    if not question:
        return None
    prices = m.get("outcomePrices") or []
    prob = 0.0
    if prices:
        prob = max((safe_float(p) or 0) for p in prices)
    for token in m.get("tokens") or []:
        p = safe_float(token.get("price"))
        if p and p > prob:
            prob = p
    prob = _clamp_prob(prob)
    volume = safe_float(m.get("volume") or m.get("volumeNum") or m.get("liquidity") or 0) or 0
    url_slug = slug or m.get("slug") or ""
    return {
        "question": question,
        "probability": round(prob, 3),
        "volume": round(volume, 0),
        "url": f"https://polymarket.com/event/{url_slug}" if url_slug else "",
        "end_date_iso": _extract_end_date(m),
    }


def _extract_metaculus_prob(q: dict) -> float | None:
    prob = q.get("community_prediction")
    if isinstance(prob, dict):
        return safe_float(prob.get("full") or prob.get("q2"))
    return safe_float(prob)


def _filter_ofac(csv_text: str, conflict: str) -> Dict[str, Any]:
    cl = (conflict or "").lower().strip()
    keywords = OFAC_CONFLICT_KEYWORDS.get("default", [])
    for k, v in OFAC_CONFLICT_KEYWORDS.items():
        if k != "default" and k in cl:
            keywords = v
            break
    try:
        reader = csv.reader(io.StringIO(csv_text))
        matches: List[Dict[str, Any]] = []
        match_keys: set[str] = set()
        for row in reader:
            if len(row) < 4:
                continue
            name = (row[1] or "").strip().lower()
            program = (row[3] or "").strip().lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                nm = (row[1] or "").strip()
                ty = (row[2] or "").strip() if len(row) > 2 else ""
                prg = (row[3] or "").strip()
                matches.append({"name": nm, "type": ty, "program": prg})
                match_keys.add(f"{nm}|{ty}|{prg}")
        return {"total_matches": len(matches), "sample": matches[:15], "error": None, "match_keys": match_keys}
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e), "match_keys": set()}


def get_brent_price() -> Dict[str, Any]:
    for getter in (
        lambda: _fetch_alpha_series("BRENT"),
        lambda: _fetch_eia_spot("PET.RBRTE.D"),
        lambda: _fetch_fred_series("DCOILBRENTEU"),
    ):
        try:
            out = getter()
            if isinstance(out, dict) and out.get("price") is not None:
                return out
        except Exception:
            continue
    return {"error": "No Brent source available (Alpha Vantage, EIA, FRED)"}


def get_wti_price() -> Dict[str, Any]:
    for getter in (
        lambda: _fetch_alpha_series("WTI"),
        lambda: _fetch_eia_spot("PET.RWTC.D"),
        lambda: _fetch_fred_series("DCOILWTICO"),
    ):
        try:
            out = getter()
            if isinstance(out, dict) and out.get("price") is not None:
                return out
        except Exception:
            continue
    return {"error": "No WTI source available (Alpha Vantage, EIA, FRED)"}


def get_gold_price() -> Dict[str, Any]:
    api_key = (os.getenv("METALS_API_KEY") or os.getenv("METALPRICEAPI_KEY") or "").strip()
    if not api_key:
        return {"error": "METALS_API_KEY not set (optional; get key at metals-api.com)"}

    async def _fetch():
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(f"{METALS_API_BASE}/latest", params={"access_key": api_key, "base": "XAU", "currencies": "USD"})
            if resp.status_code != 200:
                return {"error": f"Metals API {resp.status_code}"}
            return resp.json()

    try:
        data = run_async(_fetch())
        if isinstance(data, dict) and "error" in data:
            return data
        rates = (data.get("rates") or {}) if isinstance(data, dict) else {}
        usd = safe_float(rates.get("USD"))
        if usd is None:
            return {"error": "No USD rate in response"}
        return {"price": f"{usd:.2f}", "change_pct": "0.0%", "as_of": (data.get("date") or "")}
    except Exception as e:
        return {"error": str(e)}


def get_vix() -> Dict[str, Any]:
    for getter in (lambda: _fetch_alpha_series("VIX"), lambda: _fetch_fred_series("VIXCLS")):
        try:
            out = getter()
            if isinstance(out, dict) and out.get("price") is not None:
                return out
        except Exception:
            continue
    return {"error": "No VIX source available (Alpha Vantage, FRED)"}


def get_fear_greed() -> Dict[str, Any]:
    async def _fetch():
        async with httpx.AsyncClient(timeout=10.0) as client:
            if FEAR_GREED_CNN_API_URL:
                try:
                    resp = await client.get(FEAR_GREED_CNN_API_URL)
                    data = resp.json()
                    if isinstance(data, dict) and data.get("value") is not None:
                        return {"value": int(data.get("value")), "value_classification": data.get("value_classification")}
                except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
                    # Fall back to alternative.me source if CNN endpoint fails.
                    pass
            resp = await client.get(FEAR_GREED_FALLBACK_URL)
            data = resp.json()
            arr = data.get("data") if isinstance(data, dict) else []
            if not arr or not isinstance(arr, list):
                return {"error": "No data"}
            item = arr[0]
            value = item.get("value")
            return {"value": int(value) if value is not None else None, "value_classification": item.get("value_classification")}

    try:
        return run_async(_fetch())
    except Exception as e:
        return {"error": str(e)}


def get_polymarket_conflict_odds(conflict: str) -> List[Dict[str, Any]]:
    async def _fetch_tracked():
        headers = _polymarket_headers()
        out = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for slug in TRACKED_POLYMARKET_SLUGS:
                try:
                    resp = await client.get(f"{GAMMA_API_BASE}/events/slug/{slug}", headers=headers)
                    if resp.status_code != 200:
                        continue
                    event = resp.json()
                    if not isinstance(event, dict):
                        continue
                    item = _normalize_polymarket_item(event, slug)
                    if item and (item.get("probability") or 0) > 0 and _polymarket_end_ok(event):
                        out.append(item)
                except Exception:
                    continue
        return out

    async def _fetch_all():
        headers = _polymarket_headers()
        results = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            for endpoint in ("events", "markets"):
                try:
                    resp = await client.get(
                        f"{GAMMA_API_BASE}/{endpoint}",
                        params={"limit": 200, "active": "true", "closed": "false"},
                        headers=headers,
                    )
                    if resp.status_code == 200 and isinstance(resp.json(), list):
                        results.extend(resp.json())
                except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        return results

    try:
        tracked = run_async(_fetch_tracked())
        tracked_questions = {str(t.get("question", ""))[:80] for t in tracked if t.get("question")}
        data = run_async(_fetch_all())
        relevant = []
        seen = set()
        for m in data:
            if not _polymarket_end_ok(m):
                continue
            question = str(m.get("question") or m.get("title") or m.get("name") or "").strip()
            if not question:
                continue
            key = question[:60]
            if key in seen:
                continue
            combined = f"{question.lower()} {str(m.get('description') or '').lower()}"
            if not _matches_prediction_market_filters(combined):
                continue
            if question[:80] in tracked_questions:
                continue
            seen.add(key)
            item = _normalize_polymarket_item(m)
            if item and (item.get("probability") or 0) > 0:
                item["url"] = f"https://polymarket.com/event/{m.get('slug', '')}"
                relevant.append(item)
        relevant.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        return tracked + relevant[:10]
    except Exception as e:
        return [{"error": str(e)}]


def get_metaculus_conflict_questions(conflict: str) -> List[Dict[str, Any]]:
    async def _fetch():
        search_term = (conflict or "").strip() or "geopolitics"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                METACULUS_API_BASE,
                params={"search": search_term, "status": "open", "limit": 20, "order_by": "-activity"},
            )
            if resp.status_code != 200:
                return [{"error": f"Metaculus API {resp.status_code}"}]
            data = resp.json()
        results = data.get("results") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(results, list):
            return []
        cl = (conflict or "").lower()
        keywords = [t for t in METACULUS_CONFLICT_TERMS if t in cl] or ["war", "military", "iran", "ukraine"]
        out = []
        for q in results[:15]:
            if not isinstance(q, dict):
                continue
            title = (q.get("title") or "").strip()
            title_lower = title.lower()
            if not title or not any(kw in title_lower for kw in keywords):
                continue
            if not _matches_prediction_market_filters(title_lower):
                continue
            prob = _extract_metaculus_prob(q)
            out.append(
                {
                    "title": title[:200],
                    "probability": round(prob, 3) if prob is not None else None,
                    "url": f"https://www.metaculus.com/questions/{q.get('id', '')}",
                    "resolve_time": q.get("resolve_time"),
                }
            )
        return out[:10]

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


def get_kalshi_conflict_markets(conflict: str) -> List[Dict[str, Any]]:
    if not KALSHI_API_BASE:
        return []

    async def _fetch():
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{KALSHI_API_BASE.rstrip('/')}/events",
                    params={"limit": 50, "status": "open"},
                )
                if resp.status_code != 200:
                    return [{"error": f"Kalshi API {resp.status_code}"}]
                data = resp.json()
        except Exception as e:
            return [{"error": str(e)}]
        events = data.get("events") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(events, list):
            return []
        cl = (conflict or "").lower()
        keywords = [t for t in KALSHI_CONFLICT_TERMS if t in cl] or ["iran", "military", "war"]
        out: List[Dict[str, Any]] = []
        for ev in events[:15]:
            if not isinstance(ev, dict):
                continue
            title = (ev.get("title") or ev.get("event_ticker") or "").strip()
            title_lower = title.lower()
            if not title or not any(kw in title_lower for kw in keywords):
                continue
            prob = safe_float(ev.get("last_price")) or 0.0
            out.append(
                {
                    "question": title[:200],
                    "probability": round(prob, 3),
                    "url": f"https://kalshi.com/markets/{ev.get('event_ticker', ev.get('ticker', ''))}",
                    "volume": safe_float(ev.get("volume")) or 0,
                }
            )
        return out[:10]

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_ofac_cached(client: Any, conflict: str) -> Dict[str, Any]:
    global _ofac_raw_csv, _ofac_cache_ts, _ofac_previous_keys
    fetched_at = datetime.now(timezone.utc).isoformat()
    if _ofac_raw_csv is not None and (time.monotonic() - _ofac_cache_ts) < OFAC_CACHE_TTL:
        out = _filter_ofac(_ofac_raw_csv, conflict)
        out["fetched_at"] = fetched_at
    else:
        try:
            resp = await client.request("GET", OFAC_SDN_CSV_URL, timeout=30.0, follow_redirects=True)
            _ofac_raw_csv = resp.text
            _ofac_cache_ts = time.monotonic()
            out = _filter_ofac(_ofac_raw_csv, conflict)
            out["fetched_at"] = fetched_at
        except Exception as e:
            out = {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": fetched_at, "match_keys": set()}

    current_keys = out.get("match_keys") or set()
    out["ofac_delta"] = {
        "added_since_last_run": len(current_keys - _ofac_previous_keys),
        "previous_total": len(_ofac_previous_keys),
        "current_total": len(current_keys),
    }
    if out.get("error") is None:
        _ofac_previous_keys = current_keys
    return out


def get_ofac_sanctions_highlights(conflict: str) -> Dict[str, Any]:
    async def _run() -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            return await _fetch_ofac_cached(client, conflict)

    try:
        return run_async(_run())
    except Exception as e:
        return {"total_matches": 0, "sample": [], "error": str(e), "fetched_at": datetime.now(timezone.utc).isoformat()}


def get_tracked_wallet_positions() -> List[Dict[str, Any]]:
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
                    positions = positions if isinstance(positions, list) else []
                    items = []
                    for p in positions[:20]:
                        title = p.get("title") or p.get("market") or p.get("question") or ""
                        size = safe_float(p.get("size") or p.get("tokens") or 0)
                        avg_price = safe_float(p.get("avgPrice") or p.get("price"))
                        items.append(
                            {"title": title[:120] if title else "", "size": round(size, 2) if size else 0, "avgPrice": round(avg_price, 4) if avg_price else None}
                        )
                    out.append({"wallet": label, "address": address[:10] + "...", "position_count": len(positions), "positions": items})
                except Exception as e:
                    out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
        return out

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]


def get_tracked_chain_wallets() -> List[Dict[str, Any]]:
    api_key = (os.getenv("ETHEREUM_ETHERSCAN_API_KEY") or os.getenv("ETHERSCAN_API_KEY") or "").strip()
    addresses = (TRACKED_ETH_ADDRESSES or [])[:MAX_ETHERSCAN_ADDRESSES_PER_RUN]
    if not addresses:
        return []
    if not api_key:
        return [{"error": "ETHEREUM_ETHERSCAN_API_KEY not set"}]

    async def _fetch():
        out: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for i, (label, address) in enumerate(addresses):
                if i > 0:
                    await asyncio.sleep(ETHERSCAN_RATE_LIMIT_DELAY_SEC)
                try:
                    resp = await client.get(
                        "https://api.etherscan.io/api",
                        params={"module": "account", "action": "balance", "address": address, "tag": "latest", "apikey": api_key},
                    )
                    if resp.status_code != 200:
                        out.append({"wallet": label, "address": address[:10] + "...", "error": resp.status_code})
                        continue
                    data = resp.json()
                    if data.get("status") != "1" and data.get("message") != "OK":
                        out.append({"wallet": label, "address": address[:10] + "...", "error": data.get("message", "API error")})
                        continue
                    wei = int(data.get("result", 0))
                    out.append({"wallet": label, "address": address[:10] + "...", "balance_eth": round(wei / 1e18, 4), "balance_wei": str(wei)})
                except Exception as e:
                    out.append({"wallet": label, "address": address[:10] + "...", "error": str(e)})
        if out:
            out.append({"_attribution": "Etherscan (etherscan.io)"})
        return out

    try:
        return run_async(_fetch())
    except Exception as e:
        return [{"error": str(e)}]
