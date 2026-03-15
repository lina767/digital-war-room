"""
Key-findings assembly: appends agent-level findings to the LLM/rule-based key_findings list.
Uses only agent_results and parameters; no compliance or state.
"""
from typing import Any, Dict, List


def append_agent_findings(
    key_findings: List[str],
    agent_results: Dict[str, Any],
    conflict: str,
    chokepoint_score: float,
) -> List[str]:
    """Append agent-level key findings (NEWS, SIGINT, GEOINT, TECHINT, etc.) to the given list. Returns the same list (mutated)."""
    acled_refs = agent_results.get("acled_refs") or []
    news_result = agent_results.get("news") or {}
    sigint_result = agent_results.get("sigint") or {}
    geoint_result = agent_results.get("geoint") or {}
    socmint_result = agent_results.get("socmint") or {}
    techint_result = agent_results.get("techint") or {}
    cyber_result = agent_results.get("cyber") or {}
    energy_result = agent_results.get("energy") or {}
    protest_result = agent_results.get("protest") or {}
    diplo_result = agent_results.get("diplo") or {}
    proximity_result = agent_results.get("proximity") or {}
    chokepoint_result = agent_results.get("chokepoint") or {}

    for art in (news_result.get("articles") or [])[:3]:
        title = art.get("title") or "News article"
        source = art.get("source") or "Unknown"
        label = art.get("sentiment_label") or "NEUTRAL"
        key_findings.append(f"NEWS ({label}) – {title} [{source}]")

    for signal in (socmint_result.get("top_signals") or [])[:3]:
        key_findings.append(f"SOCMINT – {signal}")

    ac_list = sigint_result.get("aircraft") or []
    ships_list = sigint_result.get("ships") or []
    for a in ac_list[:2]:
        if isinstance(a, dict) and "error" not in a:
            key_findings.append(f"SIGINT – {a.get('category', 'aircraft')}: {a.get('flight', '?')} ({a.get('region', a.get('source', ''))})")
    if ships_list:
        key_findings.append(f"SIGINT – {len(ships_list)} warship(s) in region")
    for r in (sigint_result.get("conflict_reports") or [])[:3]:
        if isinstance(r, dict) and "error" not in r and r.get("title"):
            key_findings.append(f"SIGINT (intel) – {r.get('title', '')[:70]} [{r.get('source', '')}]")

    for h in (geoint_result.get("hotspots") or [])[:2]:
        lat = h.get("lat")
        lon = h.get("lon")
        frp = h.get("frp")
        anomaly_type = h.get("type") or "anomaly"
        key_findings.append(f"GEOINT ({anomaly_type}) – Thermal anomaly at {lat},{lon} FRP={frp}")

    for ind in (techint_result.get("tech_indicators") or [])[:2]:
        if ind.get("symbol") and "error" not in ind:
            key_findings.append(f"TECHINT – {ind.get('symbol')} {ind.get('change_pct', '')} ({ind.get('label', '')})")
    for art in (techint_result.get("export_controls") or [])[:1]:
        if art.get("title") and "error" not in art:
            key_findings.append(f"TECHINT (export controls) – {art.get('title')} [{art.get('source', '')}]")
    for ev in (techint_result.get("ioda_events") or [])[:2]:
        if isinstance(ev, dict) and "error" not in ev and ev.get("entityCode"):
            key_findings.append(f"TECHINT (IODA) – Internet outage/event in {ev.get('entityCode', '')}")
    ioda_outages = [o for o in (techint_result.get("ioda_outages") or []) if isinstance(o, dict) and "error" not in o]
    ioda_alerts = [a for a in (techint_result.get("ioda_alerts") or []) if isinstance(a, dict) and "error" not in a]
    if ioda_outages or ioda_alerts:
        key_findings.append(f"TECHINT (IODA v2) – {len(ioda_outages)} outage(s), {len(ioda_alerts)} BGP/anomaly alert(s); signals (BGP/Ping/Telescope) available.")
    if techint_result.get("ooni", {}).get("telegram_signal_blocked_iran"):
        key_findings.append("TECHINT (OONI) – Telegram/Signal confirmed blocked in Iran (escalation)")
    for o in (techint_result.get("cloudflare_outages") or [])[:1]:
        if isinstance(o, dict) and "error" not in o:
            scope = o.get("scope") or ""
            out = o.get("outage") or {}
            cause = out.get("outageCause", "") if isinstance(out, dict) else str(out)
            key_findings.append(f"TECHINT (Cloudflare) – Outage: {scope} {cause}".strip())
    if techint_result.get("shodan", {}).get("total_count"):
        key_findings.append(f"TECHINT (Shodan) – {techint_result['shodan']['total_count']} hosts in conflict region(s)")

    if cyber_result.get("cisa_kev", {}).get("total"):
        key_findings.append(f"CYBER (CISA KEV) – {cyber_result['cisa_kev']['total']} known exploited vulnerabilities")
    for r in (cyber_result.get("threat_reports") or [])[:2]:
        if isinstance(r, dict) and r.get("title") and "error" not in r:
            key_findings.append(f"CYBER – {r.get('title', '')[:60]}")
    gn = cyber_result.get("greynoise_scan_context") or {}
    if gn.get("available") and int(gn.get("count") or 0) > 0:
        key_findings.append(f"CYBER (GreyNoise) – {gn['count']} malicious scanners (7d); top actors/countries in context")

    agsi_full = energy_result.get("agsi_storage", {}).get("full") or []
    if agsi_full:
        avg = sum(float(x.get("full_pct") or 0) for x in agsi_full) / max(len(agsi_full), 1)
        key_findings.append(f"ENERGY (AGSI+) – {len(agsi_full)} storage record(s), avg fill {avg:.0f}%")
    for c in (energy_result.get("commodities") or [])[:2]:
        if c.get("symbol") and "error" not in c and c.get("price"):
            key_findings.append(f"ENERGY – {c.get('symbol')} {c.get('price')} ({c.get('change_pct', '')})")
    if conflict and "iran" in conflict.lower():
        note = energy_result.get("global_impact_note")
        if note:
            key_findings.append(f"Global impact – {note}")
        else:
            commodities = energy_result.get("commodities") or []
            valid_c = [c for c in commodities if isinstance(c, dict) and c.get("change_pct_raw") is not None and "error" not in c]
            max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
            if max_up is not None and max_up >= 2.0:
                key_findings.append(f"Global impact – Oil (Brent/WTI) {max_up:+.1f}% – potential Strait of Hormuz / chokepoint risk premium")
    if conflict and "iran" in conflict.lower():
        global_kw = ("hormuz", "hormus", "oil", "chokepoint", "strait")
        for art in (news_result.get("articles") or []):
            if not isinstance(art, dict) or "error" in art:
                continue
            title = (art.get("title") or "").lower()
            if any(kw in title for kw in global_kw):
                src = art.get("source") or "News"
                key_findings.append(f"Global impact (News) – {art.get('title', '')[:70]} [{src}]")
                break

    protest_events = protest_result.get("protest_events") or []
    valid_pe = [e for e in protest_events if isinstance(e, dict) and "error" not in e]
    if valid_pe:
        key_findings.append(f"PROTEST (ACLED) – {len(valid_pe)} protest/riot events")
    for a in (protest_result.get("protest_articles") or [])[:1]:
        if isinstance(a, dict) and a.get("title") and "error" not in a:
            key_findings.append(f"PROTEST (GDELT) – {a.get('title', '')[:55]}")

    ofac_matches = diplo_result.get("ofac_sdn", {}).get("total_matches") or 0
    if ofac_matches:
        key_findings.append(f"DIPLO (OFAC SDN) – {ofac_matches} conflict-relevant entries")
    for n in (diplo_result.get("un_icj_news") or [])[:2]:
        if isinstance(n, dict) and n.get("title") and "error" not in n:
            key_findings.append(f"DIPLO ({n.get('source', 'UN/ICJ')}) – {n.get('title', '')[:55]}")

    for ev in (proximity_result.get("evidence") or [])[:3]:
        if isinstance(ev, dict) and ev.get("summary"):
            risk = ev.get("riskLabel", "")
            key_findings.append(f"PROXIMITY ({risk}) – {ev.get('summary', '')[:75]}")

    for ref in acled_refs[:3]:
        if isinstance(ref, dict) and ref.get("title") and "error" not in str(ref.get("excerpt", ""))[:50]:
            key_findings.append(f"ACLED reference – {ref.get('title', '')[:70]}")

    for cp in (chokepoint_result.get("chokepoints") or []):
        if not isinstance(cp, dict):
            continue
        risk = cp.get("disruption_risk", 0)
        status = cp.get("status", "OPEN")
        name = cp.get("name", "")
        dq = cp.get("data_quality", "")
        if risk >= 60 or status != "OPEN":
            key_findings.append(
                f"CHOKEPOINT – {name}: {status} (risk {risk:.0f}/100, "
                f"~{cp.get('oil_flow_estimate_mbd', 0)} mbd, "
                f"{cp.get('tanker_count', 0)} tankers [{dq}])"
            )
    if chokepoint_score >= 50:
        key_findings.append(f"CHOKEPOINT – Composite chokepoint risk {chokepoint_score:.0f}/100")

    food_risk = float(energy_result.get("food_security_risk", 0))
    if food_risk >= 50:
        food_items = energy_result.get("food_commodities") or []
        food_movers = [f"{c.get('symbol')} {c.get('change_pct', '')}" for c in food_items
                       if isinstance(c, dict) and c.get("change_pct_raw") is not None
                       and abs(c.get("change_pct_raw", 0)) > 3]
        detail = f" ({', '.join(food_movers[:3])})" if food_movers else ""
        key_findings.append(
            f"Global impact – Food security risk {food_risk:.0f}/100{detail} – "
            f"chokepoint disruption threatens grain/fertilizer flows"
        )
    fao = energy_result.get("fao_fpi") or {}
    if fao.get("yoy_change_pct") and fao["yoy_change_pct"] > 10:
        key_findings.append(
            f"ENERGY (FAO FPI) – Food Price Index {fao.get('index', '?')} "
            f"({fao['yoy_change_pct']:+.1f}% YoY) – elevated global food stress"
        )

    return key_findings
