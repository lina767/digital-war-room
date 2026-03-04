"""
TECHINT Agent – Tech sector indicators, export control, IODA, OONI, Cloudflare Radar, Shodan.
Fetches: tech ETF quotes (Alpha Vantage), export-control news (NewsAPI), IODA events,
OONI measurements (Telegram/Signal confirmed_blocked in Iran = escalation), Cloudflare
Radar outages, Shodan host counts (cyber-activity indicator).
"""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
NEWS_API_URL = "https://newsapi.org/v2/everything"
IODA_EVENTS_URL = "https://ioda.inetintel.cc.gatech.edu/v2/events"
OONI_MEASUREMENTS_URL = "https://api.ooni.io/api/v1/measurements"
CLOUDFLARE_RADAR_OUTAGES_URL = "https://api.cloudflare.com/client/v4/radar/annotations/outages"
SHODAN_HOST_COUNT_URL = "https://api.shodan.io/shodan/host/count"

# Shodan: strategic port counts (no search credits; count API is free)
# port 502 = Modbus (industrial/SCADA) – exposure in conflict zone = escalation signal
# port 22 = SSH, 443 = HTTPS (general exposure)
SHODAN_PORT_QUERIES = [
    (502, "port:502", "industrial_scada"),   # Modbus – critical infrastructure
    (22, "port:22", "ssh"),
    (443, "port:443", "https"),
]

# OONI: test names for Telegram and Signal blocking detection
OONI_INSTANT_MESSAGING_TESTS = ["telegram", "signal"]

# Conflict keyword -> ISO 3166-1 alpha-2 country code(s) for IODA/Radar
CONFLICT_COUNTRY_CODES: Dict[str, List[str]] = {
    "iran": ["IR"],
    "us-iran": ["IR", "US"],
    "russia": ["RU"],
    "ukraine": ["UA"],
    "israel": ["IL"],
    "gaza": ["PS"],
    "china": ["CN"],
    "taiwan": ["TW"],
    "syria": ["SY"],
    "yemen": ["YE"],
    "iraq": ["IQ"],
    "afghanistan": ["AF"],
}

# Tech/semiconductor proxies for supply-chain and sanctions sensitivity
TECH_SYMBOLS = [
    ("SMH", "Semiconductor ETF"),
    ("QQQ", "Nasdaq-100 / Tech"),
]

EXPORT_CONTROL_QUERY = (
    '"export control" OR "export controls" OR "semiconductor sanctions" '
    'OR "chip export" OR "BIS entity list" OR "technology sanctions" '
    'OR "dual-use" OR "restricted technology"'
)
NEWS_DOMAINS = (
    "reuters.com,apnews.com,bbc.com,theguardian.com,ft.com,bloomberg.com,"
    "politico.com,defensenews.com,reuters.com,wsj.com,cnbc.com,techcrunch.com"
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_pct(change: float | None) -> str:
    if change is None:
        return "0.0%"
    return f"{change:+.1f}%"


def _conflict_to_country_codes(conflict: str) -> List[str]:
    """Map conflict string to IODA/Radar country codes (ISO 3166-1 alpha-2)."""
    cl = (conflict or "").lower().strip()
    for key, codes in CONFLICT_COUNTRY_CODES.items():
        if key in cl:
            return list(codes)
    return []


async def _fetch_ioda_events(conflict: str) -> List[Dict[str, Any]]:
    """Fetch IODA outage events for conflict-relevant countries. API: https://ioda.caida.org/ioda/api"""
    codes = _conflict_to_country_codes(conflict)
    if not codes:
        return []
    until_ts = int(time.time())
    from_ts = until_ts - (7 * 24 * 3600)  # last 7 days
    all_events: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for entity_code in codes[:3]:  # max 3 countries to avoid rate limits
            try:
                resp = await client.get(
                    IODA_EVENTS_URL,
                    params={
                        "from": from_ts,
                        "until": until_ts,
                        "entityType": "country",
                        "entityCode": entity_code,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # Normalize: API may return { "data": [...] } or { "events": [...] } or list
                events = data if isinstance(data, list) else data.get("events") or data.get("data") or []
                for ev in events if isinstance(events, list) else []:
                    if isinstance(ev, dict):
                        ev_copy = dict(ev)
                        ev_copy["entityCode"] = ev_copy.get("entityCode") or entity_code
                        all_events.append(ev_copy)
            except Exception as e:
                all_events.append({"entityCode": entity_code, "error": str(e)})
    return all_events


async def _fetch_ooni_measurements(conflict: str) -> Dict[str, Any]:
    """
    Fetch OONI measurements for Telegram/Signal in conflict-relevant countries.
    If Telegram or Signal appear as confirmed_blocked in Iran (IR) → escalation indicator.
    API: https://api.ooni.io/api/v1/
    """
    codes = _conflict_to_country_codes(conflict)
    if not codes:
        return {"measurements": [], "confirmed_blocked": [], "telegram_signal_blocked_iran": False}
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    confirmed_blocked: List[Dict[str, Any]] = []
    all_measurements: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            for probe_cc in codes[:3]:
                for test_name in OONI_INSTANT_MESSAGING_TESTS:
                    try:
                        resp = await client.get(
                            OONI_MEASUREMENTS_URL,
                            params={
                                "probe_cc": probe_cc,
                                "test_name": test_name,
                                "since": since,
                                "limit": 50,
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        results = data.get("results") or []
                        for r in results:
                            all_measurements.append({
                                "probe_cc": probe_cc,
                                "test_name": test_name,
                                "measurement_id": r.get("measurement_id"),
                                "input": r.get("input"),
                                "anomaly": r.get("anomaly"),
                                "confirmed": r.get("confirmed"),
                            })
                            # Check for confirmed_blocked (can be in r.confirmed or inside measurement)
                            is_confirmed_blocked = (
                                r.get("confirmed") is True
                                or (isinstance(r.get("confirmed"), str) and "blocked" in str(r.get("confirmed")).lower())
                            )
                            if is_confirmed_blocked:
                                confirmed_blocked.append({
                                    "probe_cc": probe_cc,
                                    "test_name": test_name,
                                    "measurement_id": r.get("measurement_id"),
                                })
                    except Exception as e:
                        all_measurements.append({"probe_cc": probe_cc, "test_name": test_name, "error": str(e)})
    except Exception as e:
        return {"measurements": [], "confirmed_blocked": [], "telegram_signal_blocked_iran": False, "error": str(e)}
    telegram_signal_blocked_iran = any(
        c.get("probe_cc") == "IR" for c in confirmed_blocked
    )
    return {
        "measurements": all_measurements[:30],
        "confirmed_blocked": confirmed_blocked,
        "telegram_signal_blocked_iran": telegram_signal_blocked_iran,
    }


async def _fetch_cloudflare_outages(token: str, conflict: str) -> List[Dict[str, Any]]:
    """Fetch Cloudflare Radar outage annotations (e.g. internet shutdowns). Last 7 days."""
    codes = _conflict_to_country_codes(conflict)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                CLOUDFLARE_RADAR_OUTAGES_URL,
                params={"limit": 20, "offset": 0, "dateRange": "7d", "format": "json"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        result = data.get("result") or {}
        annotations = result.get("annotations") or []
        # Optionally filter by conflict-relevant locations
        if codes:
            filtered = [a for a in annotations if a.get("locations") and any(loc in (a.get("locations") or []) for loc in codes)]
            if filtered:
                return filtered[:10]
        return list(annotations)[:10]
    except Exception as e:
        return [{"error": str(e)}]


async def _fetch_shodan_activity(api_key: str, conflict: str) -> Dict[str, Any]:
    """
    Shodan host count for conflict-relevant countries (count API uses no query credits).
    Adds breakdown by strategic ports: 502 (Modbus/SCADA), 22 (SSH), 443 (HTTPS).
    Industrial (port 502) exposure in conflict zone = escalation indicator.
    """
    codes = _conflict_to_country_codes(conflict)
    if not codes or not api_key:
        return {"countries": [], "total_count": 0, "port_breakdown": {}, "industrial_exposed": 0}
    countries: List[Dict[str, Any]] = []
    total = 0
    port_breakdown: Dict[str, int] = {}
    industrial_exposed = 0
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for cc in codes[:3]:
                try:
                    resp = await client.get(
                        SHODAN_HOST_COUNT_URL,
                        params={"key": api_key, "query": f"country:{cc}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    c = int(data.get("total", 0))
                    total += c
                    country_data: Dict[str, Any] = {"country": cc, "count": c, "ports": {}}
                    for port_num, port_query, label in SHODAN_PORT_QUERIES:
                        try:
                            r = await client.get(
                                SHODAN_HOST_COUNT_URL,
                                params={"key": api_key, "query": f"country:{cc} {port_query}"},
                            )
                            r.raise_for_status()
                            port_count = int(r.json().get("total", 0))
                            country_data["ports"][str(port_num)] = port_count
                            port_breakdown[label] = port_breakdown.get(label, 0) + port_count
                            if port_num == 502:
                                industrial_exposed += port_count
                        except Exception:
                            country_data["ports"][str(port_num)] = 0
                    countries.append(country_data)
                except Exception as e:
                    countries.append({"country": cc, "error": str(e)})
            # Optional: has_vuln count for first country (attack surface indicator)
            vuln_count: int | None = None
            if codes:
                try:
                    r = await client.get(
                        SHODAN_HOST_COUNT_URL,
                        params={"key": api_key, "query": f"country:{codes[0]} has_vuln:1"},
                    )
                    r.raise_for_status()
                    vuln_count = int(r.json().get("total", 0))
                except Exception:
                    pass
        out: Dict[str, Any] = {
            "countries": countries,
            "total_count": total,
            "port_breakdown": port_breakdown,
            "industrial_exposed": industrial_exposed,
        }
        if vuln_count is not None:
            out["vuln_count"] = vuln_count
        return out
    except Exception as e:
        return {"countries": [], "total_count": 0, "port_breakdown": {}, "industrial_exposed": 0, "error": str(e)}


async def _fetch_quote(client: httpx.AsyncClient, symbol: str, api_key: str) -> Dict[str, Any]:
    """Fetch GLOBAL_QUOTE for one symbol."""
    try:
        resp = await client.get(ALPHAVANTAGE_URL, params={
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        }, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        q = data.get("Global Quote") or {}
        price = _safe_float(q.get("05. price"))
        prev = _safe_float(q.get("08. previous close"))
        change_pct = ((price - prev) / prev * 100) if prev and prev != 0 else None
        return {
            "symbol": symbol,
            "price": f"{price:.2f}" if price else None,
            "change_pct": _format_pct(change_pct),
            "change_pct_raw": change_pct,
            "as_of": q.get("07. latest trading day", ""),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e), "price": None, "change_pct": "0.0%", "change_pct_raw": None}


async def _fetch_tech_indicators(api_key: str) -> List[Dict[str, Any]]:
    """Fetch quotes for all TECH_SYMBOLS."""
    results = []
    async with httpx.AsyncClient() as client:
        for symbol, _ in TECH_SYMBOLS:
            r = await _fetch_quote(client, symbol, api_key)
            r["label"] = next((l for s, l in TECH_SYMBOLS if s == symbol), symbol)
            results.append(r)
    return results


async def _fetch_export_control_news(api_key: str, conflict: str) -> List[Dict[str, Any]]:
    """Search NewsAPI for export control / tech sanctions articles."""
    try:
        from_date = datetime.now(timezone.utc) - timedelta(hours=72)
        query = f"({EXPORT_CONTROL_QUERY})"
        # Optionally narrow by conflict
        cl = (conflict or "").lower()
        if "china" in cl or "iran" in cl or "russia" in cl:
            query = f"{query} AND ({conflict})"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "relevance",
            "pageSize": 15,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "domains": NEWS_DOMAINS,
            "apiKey": api_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NEWS_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        articles = []
        for art in data.get("articles", []):
            title = (art.get("title") or "").strip()
            if not title:
                continue
            source = (art.get("source") or {}).get("name") or ""
            articles.append({
                "title": title,
                "source": source,
                "url": art.get("url"),
                "published_at": art.get("publishedAt"),
                "description": (art.get("description") or "")[:200],
            })
        return articles
    except Exception as e:
        return [{"error": str(e)}]


def _compute_techint_score(
    tech_indicators: List[Dict],
    export_articles: List[Dict],
    ioda_events: List[Dict],
    ooni_result: Dict[str, Any],
    cloudflare_outages: List[Dict],
    shodan_activity: Dict[str, Any],
) -> float:
    """Compute TECHINT escalation score 0–100 from all signals."""
    base = 30.0
    # Tech sell-off
    for ind in tech_indicators:
        raw = ind.get("change_pct_raw")
        if raw is not None and raw < -3:
            base += 12
        elif raw is not None and raw < 0:
            base += 5
    # Export control news
    valid_articles = [a for a in export_articles if "error" not in a]
    if len(valid_articles) >= 5:
        base += 25
    elif len(valid_articles) >= 2:
        base += 15
    elif len(valid_articles) >= 1:
        base += 8
    # IODA internet outage events
    valid_ioda = [e for e in ioda_events if "error" not in e]
    if len(valid_ioda) >= 3:
        base += 18
    elif len(valid_ioda) >= 1:
        base += 10
    # OONI: Telegram + Signal confirmed_blocked in Iran = strong escalation indicator
    if ooni_result.get("telegram_signal_blocked_iran"):
        base += 22
    elif ooni_result.get("confirmed_blocked"):
        base += 12
    # Cloudflare Radar outages in conflict region
    valid_cf = [o for o in cloudflare_outages if "error" not in o]
    if len(valid_cf) >= 3:
        base += 15
    elif len(valid_cf) >= 1:
        base += 8
    # Shodan: host count + industrial/SCADA exposure (port 502) in conflict zone
    total_shodan = int(shodan_activity.get("total_count") or 0)
    industrial = int(shodan_activity.get("industrial_exposed") or 0)
    vuln_count = shodan_activity.get("vuln_count")
    if total_shodan > 500000:
        base += 5
    if industrial > 500:
        base += 12   # Exposed industrial/SCADA in conflict zone = strong escalation
    elif industrial > 100:
        base += 8
    elif industrial > 0:
        base += 4
    if vuln_count is not None and int(vuln_count) > 20000:
        base += 5   # Large attack surface in region
    return min(100.0, max(0.0, base))


def _build_summary(
    tech_indicators: List[Dict],
    export_articles: List[Dict],
    ioda_events: List[Dict],
    ooni_result: Dict[str, Any],
    cloudflare_outages: List[Dict],
    shodan_activity: Dict[str, Any],
    techint_score: float,
) -> str:
    """One- or two-sentence summary."""
    valid_tech = [t for t in tech_indicators if t.get("price") and "error" not in t]
    valid_news = [a for a in export_articles if "error" not in a]
    valid_ioda = [e for e in ioda_events if "error" not in e]
    valid_cf = [o for o in cloudflare_outages if "error" not in o]
    parts = []
    if valid_tech:
        moves = [f"{t['symbol']} {t['change_pct']}" for t in valid_tech]
        parts.append(f"Tech: {', '.join(moves)}.")
    if valid_news:
        parts.append(f"Export control: {len(valid_news)} articles.")
    if valid_ioda:
        parts.append(f"IODA: {len(valid_ioda)} outage event(s).")
    if ooni_result.get("telegram_signal_blocked_iran"):
        parts.append("OONI: Telegram/Signal confirmed blocked in Iran (escalation).")
    elif ooni_result.get("confirmed_blocked"):
        parts.append(f"OONI: {len(ooni_result.get('confirmed_blocked', []))} confirmed_blocked.")
    if valid_cf:
        parts.append(f"Cloudflare Radar: {len(valid_cf)} outage(s).")
    if shodan_activity.get("total_count") or shodan_activity.get("industrial_exposed"):
        total_s = shodan_activity.get("total_count", 0)
        ind = shodan_activity.get("industrial_exposed", 0)
        vuln_s = shodan_activity.get("vuln_count")
        msg = f"Shodan: {total_s} hosts in region."
        if ind > 0:
            msg += f" {ind} industrial/SCADA (port 502) exposed."
        if vuln_s is not None:
            msg += f" {vuln_s} with known vulns (primary country)."
        parts.append(msg)
    if not parts:
        return "TECHINT: No tech, export control, IODA, OONI, Cloudflare, or Shodan data."
    return "TECHINT: " + " ".join(parts)


def run_techint_agent(conflict: str) -> Dict[str, Any]:
    """Run TECHINT: tech indicators, export control, IODA, OONI, Cloudflare Radar, Shodan."""
    av_key = os.getenv("ALPHAVANTAGE_API_KEY")
    news_key = os.getenv("NEWS_API_KEY")
    cf_token = os.getenv("CLOUDFLARE_RADAR_API_TOKEN")
    shodan_key = os.getenv("SHODAN_API_KEY")

    async def _run() -> Dict[str, Any]:
        tech_indicators = await _fetch_tech_indicators(av_key) if av_key else []
        export_controls = await _fetch_export_control_news(news_key, conflict) if news_key else []
        ioda_events = await _fetch_ioda_events(conflict)
        ooni_result = await _fetch_ooni_measurements(conflict)
        cloudflare_outages = await _fetch_cloudflare_outages(cf_token, conflict) if cf_token else []
        shodan_activity = await _fetch_shodan_activity(shodan_key, conflict) if shodan_key else {}
        techint_score = _compute_techint_score(
            tech_indicators, export_controls, ioda_events,
            ooni_result, cloudflare_outages, shodan_activity,
        )
        summary = _build_summary(
            tech_indicators, export_controls, ioda_events,
            ooni_result, cloudflare_outages, shodan_activity,
            techint_score,
        )
        return {
            "tech_indicators": tech_indicators,
            "export_controls": export_controls,
            "ioda_events": ioda_events,
            "ooni": ooni_result,
            "cloudflare_outages": cloudflare_outages,
            "shodan": shodan_activity,
            "techint_score": round(techint_score, 1),
            "summary": summary,
        }

    try:
        return asyncio.run(_run())
    except Exception as e:
        return {
            "tech_indicators": [],
            "export_controls": [{"error": str(e)}],
            "ioda_events": [],
            "ooni": {},
            "cloudflare_outages": [],
            "shodan": {},
            "techint_score": 30.0,
            "summary": f"TECHINT error: {e}",
        }
