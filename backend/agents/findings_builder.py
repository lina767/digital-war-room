"""
Key-findings assembly: appends agent-level findings to the LLM/rule-based key_findings list.
Uses only agent_results and parameters; no compliance or state.
"""

from typing import Any, Dict, List, Optional


def _append_finding(
    key_findings: List[str],
    confidences: Optional[List[str]],
    text: str,
    level: str = "medium",
) -> None:
    """Append one finding and optional parallel confidence (high | medium | low)."""
    key_findings.append(text)
    if confidences is not None:
        lv = level if level in ("high", "medium", "low") else "medium"
        confidences.append(lv)


def append_agent_findings(
    key_findings: List[str],
    agent_results: Dict[str, Any],
    conflict: str,
    chokepoint_score: float,
    confidences: Optional[List[str]] = None,
) -> List[str]:
    """Append agent-level key findings (NEWS, SIGINT, GEOINT, TECHINT, etc.). Returns the same list (mutated)."""
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
        _append_finding(
            key_findings,
            confidences,
            f"NEWS ({label}) – {title} [{source}]",
            "medium",
        )

    for signal in (socmint_result.get("top_signals") or [])[:3]:
        _append_finding(key_findings, confidences, f"SOCMINT – {signal}", "low")

    ac_list = sigint_result.get("aircraft") or []
    ships_list = sigint_result.get("ships") or []
    for a in ac_list[:2]:
        if isinstance(a, dict) and "error" not in a:
            _append_finding(
                key_findings,
                confidences,
                f"SIGINT – {a.get('category', 'aircraft')}: {a.get('flight', '?')} ({a.get('region', a.get('source', ''))})",
                "high",
            )
    if ships_list:
        _append_finding(
            key_findings,
            confidences,
            f"SIGINT – {len(ships_list)} warship(s) in region",
            "high",
        )
    for r in (sigint_result.get("conflict_reports") or [])[:3]:
        if isinstance(r, dict) and "error" not in r and r.get("title"):
            _append_finding(
                key_findings,
                confidences,
                f"SIGINT (intel) – {r.get('title', '')[:70]} [{r.get('source', '')}]",
                "medium",
            )

    for h in (geoint_result.get("hotspots") or [])[:2]:
        lat = h.get("lat")
        lon = h.get("lon")
        frp = h.get("frp")
        anomaly_type = h.get("type") or "anomaly"
        _append_finding(
            key_findings,
            confidences,
            f"GEOINT ({anomaly_type}) – Thermal anomaly at {lat},{lon} FRP={frp}",
            "high",
        )

    for ind in (techint_result.get("tech_indicators") or [])[:2]:
        if ind.get("symbol") and "error" not in ind:
            _append_finding(
                key_findings,
                confidences,
                f"TECHINT – {ind.get('symbol')} {ind.get('change_pct', '')} ({ind.get('label', '')})",
                "medium",
            )
    for art in (techint_result.get("export_controls") or [])[:1]:
        if art.get("title") and "error" not in art:
            _append_finding(
                key_findings,
                confidences,
                f"TECHINT (export controls) – {art.get('title')} [{art.get('source', '')}]",
                "medium",
            )
    for ev in (techint_result.get("ioda_events") or [])[:2]:
        if isinstance(ev, dict) and "error" not in ev and ev.get("entityCode"):
            _append_finding(
                key_findings,
                confidences,
                f"TECHINT (IODA) – Internet outage/event in {ev.get('entityCode', '')}",
                "medium",
            )
    ioda_outages = [o for o in (techint_result.get("ioda_outages") or []) if isinstance(o, dict) and "error" not in o]
    ioda_alerts = [a for a in (techint_result.get("ioda_alerts") or []) if isinstance(a, dict) and "error" not in a]
    if ioda_outages or ioda_alerts:
        _append_finding(
            key_findings,
            confidences,
            f"TECHINT (IODA v2) – {len(ioda_outages)} outage(s), {len(ioda_alerts)} BGP/anomaly alert(s); signals (BGP/Ping/Telescope) available.",
            "medium",
        )
    if techint_result.get("ooni", {}).get("telegram_signal_blocked_iran"):
        _append_finding(
            key_findings,
            confidences,
            "TECHINT (OONI) – Telegram/Signal confirmed blocked in Iran (escalation)",
            "high",
        )
    for o in (techint_result.get("cloudflare_outages") or [])[:1]:
        if isinstance(o, dict) and "error" not in o:
            scope = o.get("scope") or ""
            out = o.get("outage") or {}
            cause = out.get("outageCause", "") if isinstance(out, dict) else str(out)
            _append_finding(
                key_findings,
                confidences,
                f"TECHINT (Cloudflare) – Outage: {scope} {cause}".strip(),
                "medium",
            )
    if techint_result.get("shodan", {}).get("total_count"):
        _append_finding(
            key_findings,
            confidences,
            f"TECHINT (Shodan) – {techint_result['shodan']['total_count']} hosts in conflict region(s)",
            "low",
        )

    if cyber_result.get("cisa_kev", {}).get("total"):
        _append_finding(
            key_findings,
            confidences,
            f"CYBER (CISA KEV) – {cyber_result['cisa_kev']['total']} known exploited vulnerabilities",
            "high",
        )
    for r in (cyber_result.get("threat_reports") or [])[:2]:
        if isinstance(r, dict) and r.get("title") and "error" not in r:
            _append_finding(
                key_findings,
                confidences,
                f"CYBER – {r.get('title', '')[:60]}",
                "medium",
            )
    gn = cyber_result.get("greynoise_scan_context") or {}
    if gn.get("available") and int(gn.get("count") or 0) > 0:
        _append_finding(
            key_findings,
            confidences,
            f"CYBER (GreyNoise) – {gn['count']} malicious scanners (7d); top actors/countries in context",
            "medium",
        )

    agsi_full = energy_result.get("agsi_storage", {}).get("full") or []
    if agsi_full:
        avg = sum(float(x.get("full_pct") or 0) for x in agsi_full) / max(len(agsi_full), 1)
        _append_finding(
            key_findings,
            confidences,
            f"ENERGY (AGSI+) – {len(agsi_full)} storage record(s), avg fill {avg:.0f}%",
            "medium",
        )
    for c in (energy_result.get("commodities") or [])[:2]:
        if c.get("symbol") and "error" not in c and c.get("price"):
            _append_finding(
                key_findings,
                confidences,
                f"ENERGY – {c.get('symbol')} {c.get('price')} ({c.get('change_pct', '')})",
                "medium",
            )
    if conflict and "iran" in conflict.lower():
        note = energy_result.get("global_impact_note")
        if note:
            _append_finding(key_findings, confidences, f"Global impact – {note}", "high")
        else:
            commodities = energy_result.get("commodities") or []
            valid_c = [
                c
                for c in commodities
                if isinstance(c, dict) and c.get("change_pct_raw") is not None and "error" not in c
            ]
            max_up = max((c.get("change_pct_raw") for c in valid_c), default=None)
            if max_up is not None and max_up >= 2.0:
                _append_finding(
                    key_findings,
                    confidences,
                    f"Global impact – Oil (Brent/WTI) {max_up:+.1f}% – potential Strait of Hormuz / chokepoint risk premium",
                    "high",
                )
    if conflict and "iran" in conflict.lower():
        global_kw = ("hormuz", "hormus", "oil", "chokepoint", "strait")
        for art in news_result.get("articles") or []:
            if not isinstance(art, dict) or "error" in art:
                continue
            title = (art.get("title") or "").lower()
            if any(kw in title for kw in global_kw):
                src = art.get("source") or "News"
                _append_finding(
                    key_findings,
                    confidences,
                    f"Global impact (News) – {art.get('title', '')[:70]} [{src}]",
                    "high",
                )
                break

    protest_events = protest_result.get("protest_events") or []
    valid_pe = [e for e in protest_events if isinstance(e, dict) and "error" not in e]
    if valid_pe:
        _append_finding(
            key_findings,
            confidences,
            f"PROTEST (ACLED) – {len(valid_pe)} protest/riot events",
            "medium",
        )
    for a in (protest_result.get("protest_articles") or [])[:1]:
        if isinstance(a, dict) and a.get("title") and "error" not in a:
            _append_finding(
                key_findings,
                confidences,
                f"PROTEST (GDELT) – {a.get('title', '')[:55]}",
                "medium",
            )

    ofac_matches = diplo_result.get("ofac_sdn", {}).get("total_matches") or 0
    if ofac_matches:
        _append_finding(
            key_findings,
            confidences,
            f"DIPLO (OFAC SDN) – {ofac_matches} conflict-relevant entries",
            "medium",
        )
    for n in (diplo_result.get("un_icj_news") or [])[:2]:
        if isinstance(n, dict) and n.get("title") and "error" not in n:
            _append_finding(
                key_findings,
                confidences,
                f"DIPLO ({n.get('source', 'UN/ICJ')}) – {n.get('title', '')[:55]}",
                "medium",
            )

    for ev in (proximity_result.get("evidence") or [])[:3]:
        if isinstance(ev, dict) and ev.get("summary"):
            risk = str(ev.get("riskLabel", "") or "").upper()
            lv = "high" if any(x in risk for x in ("CRITICAL", "HIGH", "EXTREME")) else "medium"
            _append_finding(
                key_findings,
                confidences,
                f"PROXIMITY ({ev.get('riskLabel', '')}) – {ev.get('summary', '')[:75]}",
                lv,
            )

    for ref in acled_refs[:3]:
        if isinstance(ref, dict) and ref.get("title") and "error" not in str(ref.get("excerpt", ""))[:50]:
            _append_finding(
                key_findings,
                confidences,
                f"ACLED reference – {ref.get('title', '')[:70]}",
                "high",
            )

    for cp in chokepoint_result.get("chokepoints") or []:
        if not isinstance(cp, dict):
            continue
        risk = cp.get("disruption_risk", 0)
        status = cp.get("status", "OPEN")
        name = cp.get("name", "")
        dq = cp.get("data_quality", "")
        if risk >= 60 or status != "OPEN":
            _append_finding(
                key_findings,
                confidences,
                f"CHOKEPOINT – {name}: {status} (risk {risk:.0f}/100, "
                f"~{cp.get('oil_flow_estimate_mbd', 0)} mbd, "
                f"{cp.get('tanker_count', 0)} tankers [{dq}])",
                "high",
            )
    if chokepoint_score >= 50:
        _append_finding(
            key_findings,
            confidences,
            f"CHOKEPOINT – Composite chokepoint risk {chokepoint_score:.0f}/100",
            "high",
        )

    pentagon_result = agent_results.get("pentagon_signals") or {}
    ps = pentagon_result.get("pentagon_signals_score")
    if isinstance(ps, (int, float)) and float(ps) >= 45:
        _append_finding(
            key_findings,
            confidences,
            f"PENTAGON_SIGNALS – informal DC-area venue busyness proxy {float(ps):.0f}/100 "
            "(anecdotal; not verified military activity)",
            "low",
        )

    food_risk = float(energy_result.get("food_security_risk", 0))
    if food_risk >= 50:
        food_items = energy_result.get("food_commodities") or []
        food_movers = [
            f"{c.get('symbol')} {c.get('change_pct', '')}"
            for c in food_items
            if isinstance(c, dict) and c.get("change_pct_raw") is not None and abs(c.get("change_pct_raw", 0)) > 3
        ]
        detail = f" ({', '.join(food_movers[:3])})" if food_movers else ""
        _append_finding(
            key_findings,
            confidences,
            f"Global impact – Food security risk {food_risk:.0f}/100{detail} – "
            f"chokepoint disruption threatens grain/fertilizer flows",
            "high",
        )
    fao = energy_result.get("fao_fpi") or {}
    if fao.get("yoy_change_pct") and fao["yoy_change_pct"] > 10:
        _append_finding(
            key_findings,
            confidences,
            f"ENERGY (FAO FPI) – Food Price Index {fao.get('index', '?')} "
            f"({fao['yoy_change_pct']:+.1f}% YoY) – elevated global food stress",
            "medium",
        )

    return key_findings
