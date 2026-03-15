"""
Compliance enrichment for supervisor synthesis: geofencing, AIS anomalies,
supply-chain screening, risk score, and centralised alerts. Stateless; state
(previous_sigint, previous_sigint_ts) is passed in and updated values returned.
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from compliance.ais_anomaly import analyze_ais_anomalies
from compliance.geofencing import check_sigint_for_sanctions
from compliance.risk_score import compute_compliance_risk
from compliance.supply_chain import screen_route


def build_compliance_and_alerts(
    sigint_data: Dict[str, Any],
    conflict: str,
    threat_level: str,
    diplo_result: Dict[str, Any],
    agent_results: Dict[str, Any],
    previous_sigint: Optional[Dict[str, Any]],
    previous_sigint_ts: Optional[float],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[float]]:
    """
    Build compliance dict and centralised alerts list. Returns
    (compliance_dict, alerts_list, updated_previous_sigint, updated_previous_sigint_ts).
    When sigint_data has ships, the last two return values are (sigint_data, time.time());
    otherwise the passed-through previous_sigint / previous_sigint_ts.
    """
    geofencing_alerts = check_sigint_for_sanctions(sigint_data, conflict=conflict)
    ais_anomalies = analyze_ais_anomalies(
        sigint_data,
        previous_sigint=previous_sigint,
        previous_run_ts=previous_sigint_ts,
    )
    updated_previous_sigint = sigint_data if sigint_data.get("ships") else previous_sigint
    updated_previous_sigint_ts = time.time() if sigint_data.get("ships") else previous_sigint_ts

    supply_chain_result = None
    ships_for_screening = [
        s for s in (sigint_data.get("ships") or [])
        if isinstance(s, dict) and s.get("lat") is not None and s.get("lon") is not None
    ]
    if ships_for_screening:
        waypoints = [
            {
                "label": s.get("name") or s.get("mmsi") or "vessel",
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "country_code": (s.get("flag") or "")[:2],
                "port_type": "vessel",
            }
            for s in ships_for_screening[:30]
        ]
        try:
            supply_chain_result = screen_route(
                route_label=f"SIGINT auto-screen ({conflict})",
                waypoints=waypoints,
            )
        except Exception:
            supply_chain_result = None

    ofac_sdn = diplo_result.get("ofac_sdn") or {}
    eu_sanctions = diplo_result.get("eu_sanctions") or {}
    risk_score = compute_compliance_risk(
        geofencing_alerts=geofencing_alerts,
        ais_anomalies=ais_anomalies,
        supply_chain_result=supply_chain_result,
        escalation_level=threat_level,
        conflict=conflict,
        ofac_sdn=ofac_sdn,
        eu_sanctions=eu_sanctions,
    )
    ofac_recent = diplo_result.get("ofac_recent_actions") or []

    sigint_result = agent_results.get("sigint") or {}
    alerts: List[Dict[str, Any]] = []
    for a in (sigint_result.get("alerts") or []):
        if isinstance(a, str):
            severity = "high" if ("DOOMSDAY" in a or "⚠" in a) else "medium"
            alerts.append({"source": "sigint", "severity": severity, "text": a})
    for g in geofencing_alerts:
        if isinstance(g, dict):
            alerts.append({
                "source": "geofencing",
                "severity": "high",
                "text": f"{g.get('asset_type', 'asset')} {g.get('asset_name', g.get('asset_id', ''))} in {g.get('zone_name', '')}",
            })
    for ai in ais_anomalies:
        if isinstance(ai, dict):
            alerts.append({
                "source": "ais_anomaly",
                "severity": (ai.get("severity") or "medium").lower(),
                "text": ai.get("detail", str(ai.get("anomaly_type", "anomaly"))),
            })
    cyber_data = agent_results.get("cyber") or {}
    for ga in (cyber_data.get("greynoise_alerts") or cyber_data.get("alerts") or [])[:10]:
        if isinstance(ga, str):
            alerts.append({"source": "greynoise", "severity": "medium", "text": ga})

    aircraft_list = [a for a in (sigint_data.get("aircraft") or []) if isinstance(a, dict) and "error" not in a and a.get("lat") is not None and a.get("lon") is not None]
    ships_list = [s for s in (sigint_data.get("ships") or []) if isinstance(s, dict) and "error" not in s and s.get("lat") is not None and s.get("lon") is not None]
    compliance = {
        "geofencing_alerts": geofencing_alerts,
        "ais_anomalies": ais_anomalies,
        "risk_score": risk_score,
        "sigint_window_summary": {
            "aircraft_count": len(aircraft_list),
            "ships_count": len(ships_list),
            "in_sanctions_zones": len(geofencing_alerts),
        },
        "ofac_sdn": {
            "total_matches": ofac_sdn.get("total_matches", 0),
            "sample": (ofac_sdn.get("sample") or [])[:10],
            "programs": (ofac_sdn.get("programs") or [])[:10],
            "error": ofac_sdn.get("error"),
        },
        "eu_sanctions": {
            "keyword_mentions": eu_sanctions.get("keyword_mentions", 0),
            "error": eu_sanctions.get("error"),
        },
        "ofac_recent_actions": [
            {"title": a.get("title"), "url": a.get("url"),
             "published": a.get("published"), "source": a.get("source"),
             "summary": a.get("summary")}
            for a in ofac_recent[:5]
        ],
        "disclaimer": (
            "Intelligence signals only – not legal advice. "
            "Supports due diligence but does not replace legal review."
        ),
    }
    return compliance, alerts, updated_previous_sigint, updated_previous_sigint_ts
