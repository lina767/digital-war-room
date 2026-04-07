#!/usr/bin/env python3
"""
Check all intelligence agents for functionality.
Run from backend/ with venv activated:
  cd backend && source venv/bin/activate && python scripts/check_agents.py
Optional: python scripts/check_agents.py -v   # show data hints (e.g. article count, outages)
ACLED: python scripts/check_agents.py --test-acled   # OAuth + time-window sample (Research lag)
"""

import os
import sys
from datetime import datetime

# Ensure backend root is on path and load .env
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)
os.chdir(BACKEND_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Required env vars per agent (only those without which the agent would fail entirely)
AGENT_ENV = {
    "finint": ["ALPHAVANTAGE_API_KEY"],
    "sigint": [],
    "news": [],  # RSS always available; NEWS_API_KEY / NEWSDATA_API_KEY / GNEWS_API_KEY / THE_GUARDIAN_API_KEY optional
    "geoint": ["NASA_FIRMS_KEY"],
    "satintel": [],  # Sentinel Hub creds optional; agent runs in degraded mode without them
    "socmint": [],
    "techint": [],  # Alpha Vantage, News, Cloudflare, Shodan are optional; agent runs without
    "cyber": [],  # CISA KEV no key; OTX optional
    "energy": [],  # AGSI, Alpha Vantage optional
    "diplo": [],  # OFAC/EU/UN/ICJ no key
}

CONFLICT = "Iran"


def run_one(name: str, run_fn, required_keys: list) -> tuple[bool, str, dict]:
    """Run one agent; return (success, message, result_or_error_dict)."""
    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        return False, f"Missing env: {', '.join(missing)}", {}
    start = datetime.now()
    try:
        result = run_fn(CONFLICT)
        elapsed = (datetime.now() - start).total_seconds()
        if not isinstance(result, dict):
            return False, f"Returned {type(result).__name__}, expected dict", {}
        # Brief sanity: agent should return something meaningful
        if name == "finint" and "escalation_score" not in result and "brent" not in result:
            return False, "Missing expected keys (e.g. escalation_score, brent)", result
        if name == "sigint" and "sigint_score" not in result:
            return False, "Missing sigint_score", result
        if name == "news" and "news_score" not in result:
            return False, "Missing news_score", result
        if name == "geoint" and "geoint_score" not in result:
            return False, "Missing geoint_score", result
        if name == "socmint" and "socmint_score" not in result:
            return False, "Missing socmint_score", result
        if name == "satintel" and "satintel_score" not in result:
            return False, "Missing satintel_score", result
        if name == "techint" and "techint_score" not in result:
            return False, "Missing techint_score", result
        if name == "cyber" and "cyber_score" not in result:
            return False, "Missing cyber_score", result
        if name == "energy" and "energy_score" not in result:
            return False, "Missing energy_score", result
        if name == "diplo" and "diplo_score" not in result:
            return False, "Missing diplo_score", result
        score_key = {
            "finint": "escalation_score",
            "sigint": "sigint_score",
            "news": "news_score",
            "geoint": "geoint_score",
            "socmint": "socmint_score",
            "satintel": "satintel_score",
            "techint": "techint_score",
            "cyber": "cyber_score",
            "energy": "energy_score",
            "diplo": "diplo_score",
        }.get(name)
        score = result.get(score_key, "?")
        return True, f"OK (score={score}, {elapsed:.1f}s)", result
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        return False, f"Error after {elapsed:.1f}s: {e}", {"error": str(e)}


def data_hint(name: str, data: dict) -> str:
    """One-line hint on what data the agent returned."""
    if not data:
        return "no data"
    hints = []
    if name == "finint":
        if data.get("brent"):
            hints.append("brent ✓")
        if data.get("wti"):
            hints.append("wti ✓")
        if data.get("gold") and isinstance(data.get("gold"), dict) and "error" not in data.get("gold", {}):
            hints.append("gold ✓")
        hints.append(f"polymarket={len(data.get('polymarket') or [])}")
        hints.append(f"metaculus={len(data.get('metaculus') or [])}")
        ofac = data.get("ofac_sanctions") or {}
        if isinstance(ofac, dict) and ofac.get("total_matches") is not None:
            hints.append(f"ofac_sanctions={ofac.get('total_matches', 0)}")
        hints.append(f"chain_wallets={len(data.get('tracked_chain_wallets') or [])}")
    elif name == "sigint":
        hints.append(f"aircraft={len(data.get('aircraft') or [])}")
        hints.append(f"ships={len(data.get('ships') or [])}")
        hints.append(f"notams={len(data.get('notams') or [])}")
    elif name == "news":
        hints.append(f"articles={len(data.get('articles') or [])}")
        if data.get("source_breakdown"):
            hints.append(f"sources={data['source_breakdown']}")
    elif name == "geoint":
        hints.append(f"anomalies={len(data.get('anomalies') or [])}")
    elif name == "socmint":
        hints.append(f"signals={len(data.get('top_signals') or [])}")
    elif name == "satintel":
        hints.append(f"imagery_signals={len(data.get('imagery_signals') or [])}")
        products = data.get("copernicus_products") or []
        if products and isinstance(products[0], dict):
            hints.append(f"copernicus_products={products[0].get('count', 0)}")
    elif name == "techint":
        hints.append(f"tech_indicators={len(data.get('tech_indicators') or [])}")
        hints.append(f"export_controls={len(data.get('export_controls') or [])}")
        hints.append(f"ioda={len(data.get('ioda_events') or [])}")
        if data.get("ooni"):
            hints.append(f"ooni_blocked_IR={data['ooni'].get('telegram_signal_blocked_iran', False)}")
        hints.append(f"cloudflare_outages={len(data.get('cloudflare_outages') or [])}")
        hints.append(f"shodan_total={data.get('shodan', {}).get('total_count', 0)}")
        if data.get("wayback") and (data.get("wayback") or {}).get("snapshots"):
            hints.append(f"wayback={len((data['wayback'].get('snapshots') or []))}")
        if data.get("whois_dns") and isinstance(data.get("whois_dns"), dict):
            hints.append(f"whois_domains={len(data['whois_dns'].get('results') or [])}")
        if data.get("wigle") and isinstance(data.get("wigle"), dict):
            hints.append(f"wigle_total={data['wigle'].get('total_results', 0)}")
    elif name == "cyber":
        hints.append(f"cisa_kev={data.get('cisa_kev', {}).get('total', 0)}")
        hints.append(f"threat_reports={len(data.get('threat_reports') or [])}")
        gn = data.get("greynoise_scan_context") or {}
        if gn.get("available") and gn.get("count") is not None:
            hints.append(f"greynoise_scan={gn.get('count', 0)}")
    elif name == "energy":
        hints.append(f"commodities={len(data.get('commodities') or [])}")
        hints.append(f"food_commodities={len(data.get('food_commodities') or [])}")
    elif name == "diplo":
        hints.append(f"ofac_matches={data.get('ofac_sdn', {}).get('total_matches', 0)}")
        hints.append(f"un_icj_news={len(data.get('un_icj_news') or [])}")
    return " | ".join(hints) if hints else "keys: " + ", ".join(list(data.keys())[:5])


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    print("=" * 60)
    print("Agent functionality check")
    print(f"Conflict: {CONFLICT}")
    print("=" * 60)

    agents = [
        ("finint", "run_finint_agent", AGENT_ENV["finint"]),
        ("sigint", "run_sigint_agent", AGENT_ENV["sigint"]),
        ("news", "run_news_agent", AGENT_ENV["news"]),
        ("geoint", "run_geoint_agent", AGENT_ENV["geoint"]),
        ("satintel", "run_satintel_agent", AGENT_ENV["satintel"]),
        ("socmint", "run_socmint_agent", AGENT_ENV["socmint"]),
        ("techint", "run_techint_agent", AGENT_ENV["techint"]),
        ("cyber", "run_cyber_agent", AGENT_ENV["cyber"]),
        ("energy", "run_energy_agent", AGENT_ENV["energy"]),
        ("diplo", "run_diplo_agent", AGENT_ENV["diplo"]),
    ]

    results = []
    for name, fn_name, required_keys in agents:
        print(f"\n--- {name.upper()} ---")
        try:
            mod_path = f"agents.{name}_agent"
            mod = __import__(mod_path, fromlist=[fn_name])
            run_fn = getattr(mod, fn_name)
        except Exception as e:
            print(f"  FAIL: Could not import – {e}")
            results.append((name, False, str(e), {}))
            continue
        ok, msg, data = run_one(name, run_fn, required_keys)
        results.append((name, ok, msg, data))
        status = "OK" if ok else "FAIL"
        print(f"  {status}: {msg}")
        if verbose and ok and isinstance(data, dict):
            print(f"  Data: {data_hint(name, data)}")
        if not ok and isinstance(data, dict) and data.get("error"):
            print(f"  Error detail: {data['error'][:200]}")

    print("\n" + "=" * 60)
    ok_count = sum(1 for _, ok, _, _ in results if ok)
    print(f"Summary: {ok_count}/{len(results)} agents OK")
    for name, ok, msg, data in results:
        print(f"  {name}: {'OK' if ok else 'FAIL'} – {msg}")
        if verbose and ok and data:
            print(f"       → {data_hint(name, data)}")
    print("=" * 60)
    if not verbose and ok_count == len(results):
        print("Tip: run with -v to see data hints (e.g. article/outage counts).")
    print(
        "Env vars for full data: ALPHAVANTAGE_API_KEY, NEWS_API_KEY, NEWSDATA_API_KEY, GNEWS_API_KEY, "
        "THE_GUARDIAN_API_KEY, NASA_FIRMS_KEY,"
    )
    print(
        "  CLOUDFLARE_RADAR_API_TOKEN, SHODAN_API_KEY, OTX_API_KEY, GREYNOISE_API_KEY, "
        "ACLED_EMAIL+ACLED_PASSWORD (or ACLED_API_KEY legacy)"
    )
    print("  (see backend/.env.example or .env)")
    return 0 if ok_count == len(results) else 1


def test_acled():
    """Direct ACLED OAuth + API test."""
    import httpx

    email = os.getenv("ACLED_EMAIL", "")
    pw = os.getenv("ACLED_PASSWORD", "")
    print(f"Email: {email}")
    print(f"Password set: {bool(pw)}")
    if not email or not pw:
        print("FAIL: Set ACLED_EMAIL + ACLED_PASSWORD in backend/.env")
        return
    print("\n--- OAuth token request ---")
    r = httpx.post(
        "https://acleddata.com/oauth/token",
        data={"username": email, "password": pw, "grant_type": "password", "client_id": "acled"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text[:500]}")
        return
    token = r.json().get("access_token", "")
    print(f"Token received: {bool(token)} (len={len(token)})")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for label, days_back in [("Recent (90d)", 90), ("6-12 months", 270), ("12-18 months", 450)]:
        from datetime import timedelta

        end_d = datetime.now()
        start_d = end_d - timedelta(days=days_back)
        start_d2 = end_d - timedelta(days=days_back + 180)
        date_val = f"{start_d2.strftime('%Y-%m-%d')}|{start_d.strftime('%Y-%m-%d')}"
        r2 = httpx.get(
            "https://acleddata.com/api/acled/read",
            params={
                "_format": "json",
                "country": "Iran",
                "event_type": "Protests",
                "event_date": date_val,
                "event_date_where": "BETWEEN",
                "limit": 5,
            },
            headers=headers,
            timeout=15.0,
        )
        b = r2.json()
        print(f"\n{label}: count={b.get('count')}, records={len(b.get('data', []))}")
        if b.get("data"):
            print(f"  First date: {b['data'][0].get('event_date')}")

    print("\n--- Summary ---")
    print(
        "If OAuth succeeded but 'Recent (90d)' is empty while older windows have rows, "
        "this matches typical ACLED Research-tier publication lag (not an app bug)."
    )
    print("See docs/ACLED-TROUBLESHOOTING.md and docs/ACLED-API-REFERENCE.md §13.")


def test_gdelt():
    """Direct GDELT DOC 2.0 API test."""
    import time

    import httpx

    print("Waiting 8s for rate limit clearance...")
    time.sleep(8)
    r = httpx.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={"query": "Iran unrest", "mode": "artlist", "format": "json", "maxrecords": 5, "timespan": "72H"},
        timeout=20.0,
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type', '')}")
    if r.status_code == 200:
        ct = r.headers.get("content-type", "").lower()
        if "json" in ct or "javascript" in ct:
            data = r.json()
            for key in ("articles", "articleList", "results"):
                v = data.get(key) if isinstance(data, dict) else None
                if isinstance(v, list):
                    print(f'Key "{key}": {len(v)} articles')
                    if v:
                        print(f"First title: {v[0].get('title', '?')[:100]}")
                    break
            else:
                print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
        else:
            print(f"Body: {r.text[:300]}")
    else:
        print(f"Body: {r.text[:300]}")


if __name__ == "__main__":
    if "--test-acled" in sys.argv:
        test_acled()
    elif "--test-gdelt" in sys.argv:
        test_gdelt()
    else:
        sys.exit(main())
